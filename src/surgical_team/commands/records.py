"""Record commands: check, reclaim, journal, show, list, verify."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys

from ..authority import effective_authority, integrity_problems, verdict_for
from ..gitutil import git, worktree_git
from ..ledger import Leases, Ledger, transition
from ..model import DEFAULT_CHECK_TIMEOUT, StError, iso, now
from ..status import render_status
from ..types import JSON, State


def cmd_check(args: argparse.Namespace) -> int:
    ledger = Ledger.at()
    order = ledger.order(args.order)
    if order["state"] not in ("dispatched", "reported", "deferred"):
        raise StError(f"{order['id']} is {order['state']}; nothing to check")
    level, _, source = effective_authority(ledger, order)
    if level is None and not source.startswith("approval expired"):
        # Checks are shell commands; run only ones the surgeon signed. An
        # expired approval still proves the surgeon signed these commands;
        # expiry bounds agent authority, not re-running the checks.
        raise StError(
            f"refusing to run checks: {order['id']} has no valid authority ({source})"
        )
    dispatched_workspace = order.get("dispatch", {}).get("workspace")
    workspace = ledger.workspace(order["id"]) if dispatched_workspace else None
    cwd = workspace or ledger.root
    if workspace is not None:
        head = worktree_git(["rev-parse", "HEAD"], ledger, workspace, check=False)
        dirty = bool(worktree_git(
            ["status", "--porcelain"], ledger, workspace, check=False
        ))
    else:
        head = git(["rev-parse", "HEAD"], ledger.root, check=False)
        dirty = bool(git(["status", "--porcelain"], ledger.root, check=False))
    timeout = int(order["spec"].get("check_timeout", DEFAULT_CHECK_TIMEOUT))
    results: list[JSON] = []
    ok_all = True
    for index, criterion in enumerate(order["spec"]["acceptance"], 1):
        if "check" not in criterion:
            results.append(
                {"n": index, "text": criterion["text"], "check": None, "ok": None}
            )
            continue
        try:
            completed = subprocess.run(
                criterion["check"],
                check=False, shell=True,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            output = (completed.stdout + completed.stderr)[-4000:]
            code: int | None = completed.returncode
        except subprocess.TimeoutExpired:
            output, code = f"timed out after {timeout}s", None
        ok = code == 0
        ok_all &= ok
        results.append(
            {
                "n": index,
                "text": criterion["text"],
                "check": criterion["check"],
                "exit": code,
                "ok": ok,
                "output_tail": output,
            }
        )
    run: JSON = {
        "at": iso(now()),
        "cwd": str(cwd),
        "head": head,
        "dirty": dirty,
        "results": results,
    }
    with ledger.lock():
        path = ledger.attempt_path("checks", order["id"], order["attempt"])
        record: JSON = (
            ledger._read(path)
            if path.exists()
            else {"order": order["id"], "attempt": order["attempt"], "runs": []}
        )
        record["runs"].append(run)
        ledger._write(path, record)
        ledger.event("checked", order=order["id"], attempt=order["attempt"], ok=ok_all)
        render_status(ledger)
    for result in results:
        mark = "-" if result["ok"] is None else ("PASS" if result["ok"] else "FAIL")
        print(f"  [{mark}] {result['n']}. {result['text']}")
    print(
        f"{order['id']}: {'all checks passed' if ok_all else 'CHECKS FAILED'} "
        f"at {head[:12]}{' (dirty tree)' if dirty else ''}"
    )
    return 0 if ok_all else 1


def cmd_reclaim(args: argparse.Namespace) -> None:
    ledger = Ledger.at()
    with ledger.lock():
        order = ledger.order(args.order)
        if order["state"] != "dispatched":
            raise StError(f"{order['id']} is {order['state']}, not dispatched")
        target: State = "approved" if order.get("approval") else "drafted"
        Leases(ledger.root).close(order["id"], "reclaimed")
        transition(ledger, order, target, note=f"reclaimed: {args.reason}")
        ledger.save_order(order)
        render_status(ledger)
    print(
        f"{order['id']} reclaimed to {target}; the workspace is kept. Dispatch again to retry."
    )


def cmd_journal(args: argparse.Namespace) -> None:
    ledger = Ledger.at()
    text = sys.stdin.read().strip()
    if not text:
        raise StError("journal entry is empty")
    with ledger.lock():
        path = ledger.dir / "journal" / f"{now().strftime('%Y-%m-%d')}.md"
        with open(path, "a") as handle:
            handle.write(f"\n## {iso(now())}\n\n{text}\n")
        ledger.event("journal", file=path.name)
    print(f"appended to {path.relative_to(ledger.root)}")


def cmd_show(args: argparse.Namespace) -> None:
    ledger = Ledger.at()
    order = ledger.order(args.order)
    level, push, source = effective_authority(ledger, order)
    output: JSON = {
        "order": order,
        "authority": {"level": level, "push": push, "source": source},
        "verdict": verdict_for(ledger, order),
    }
    for kind in ("reports", "checks"):
        output[kind[:-1]] = ledger.attempt_record(
            kind, order["id"], order.get("attempt", 0)
        )
    print(json.dumps(output, indent=2, ensure_ascii=False))


def cmd_list(args: argparse.Namespace) -> None:
    ledger = Ledger.at()
    for order in ledger.orders():
        if args.state and order["state"] != args.state:
            continue
        spec = order["spec"]
        print(
            f"{order['id']}  {order['state']:<10} {spec['role']:<22} "
            f"{spec['authority']}  {spec['title']}"
        )


def cmd_verify(args: argparse.Namespace) -> int:
    ledger = Ledger.at()
    problems = integrity_problems(ledger)
    for problem in problems:
        print(f"  {problem}")
    print(
        "ledger signatures verified"
        if not problems
        else f"{len(problems)} integrity problem(s)"
    )
    return 1 if problems else 0
