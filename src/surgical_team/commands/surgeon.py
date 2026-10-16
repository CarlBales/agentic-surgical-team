"""Surgeon-only commands; each signs with the surgeon's key."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path

from ..authority import decision_status
from ..ledger import write_format, Leases, Ledger, transition
from ..model import LEVELS, NAMESPACE, TERMINAL, VERSION, StError, iso, now, sha
from ..roles import is_role
from ..signing import config_dir, load_config, sign
from ..status import render_status
from ..types import JSON, State
from .footprint import release_workspace


def cmd_setup(args: argparse.Namespace) -> None:
    key = Path(args.key).expanduser().resolve()
    public_key = key if key.suffix == ".pub" else key.with_name(key.name + ".pub")
    if not public_key.exists():
        raise StError(f"no public key at {public_key}")
    # The guard stops agents from *running* ssh-keygen, but code an agent runs
    # inside its workspace is not parsed. If the key signs without the
    # surgeon (no passphrase, no touch), that code could sign an approval.
    hardware = public_key.read_text().startswith("sk-")
    if key != public_key and not hardware and not args.allow_unencrypted:
        result = subprocess.run(
            ["ssh-keygen", "-y", "-P", "", "-f", str(key)],
            check=False, capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            raise StError(
                f"{key} has no passphrase, so any process running as you can sign approvals "
                "with it, including code an agent runs in its workspace. Use a passphrase "
                "key, a hardware key (ed25519-sk), or an ssh-agent key added with "
                "`ssh-add -c` (pass the .pub path). --allow-unencrypted overrides this for "
                "throwaway test setups."
            )
    directory = config_dir()
    directory.mkdir(parents=True, exist_ok=True)
    os.chmod(directory, 0o700)
    config = load_config()
    config.update({"key": str(key), "identity": args.identity})
    (directory / "config.json").write_text(json.dumps(config, indent=2) + "\n")
    line = f'{args.identity} namespaces="{NAMESPACE}" {public_key.read_text().strip()}\n'
    signers = directory / "allowed_signers"
    existing = signers.read_text() if signers.exists() else ""
    if line not in existing:
        with open(signers, "a") as handle:
            handle.write(line)
    print(f"configured {args.identity} with {key}\ntrust root: {signers}")


def cmd_init(args: argparse.Namespace) -> None:
    ledger = Ledger.at()
    ledger.dir.mkdir(exist_ok=True)
    for subdirectory in Ledger.SUBDIRS:
        (ledger.dir / subdirectory).mkdir(exist_ok=True)
    gitignore = ledger.dir / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text(".lock\n*.tmp\n")
    if not (ledger.dir / "format.json").exists():
        if any(ledger.dir.glob("orders/WO-*.json")):
            raise StError(f"{ledger.dir} holds an existing format-0 ledger; run: st migrate")
        write_format(ledger)
    ledger.event("init", version=VERSION)
    if args.default_standing:
        with ledger.lock():
            decision = ledger.next_decision_id()
            payload: JSON = {
                "kind": "standing",
                "id": decision,
                "role": "*",
                "max_authority": "L0",
                "budget_minutes": 30,
                "scope": "Read-only analysis, review, and option papers; no changes anywhere",
                "expires": None,
                "title": "Default standing order: L0 work needs no per-order approval",
                "at": iso(now()),
            }
            ledger._write(
                ledger.dir / "decisions" / f"{decision}.json",
                {"id": decision, "signed": sign(payload)},
            )
            ledger.event("decided", decision=decision, kind="standing")
        print(f"filed {decision}: L0 orders for every role dispatch without per-order approval")
    render_status(ledger)
    print(f"ledger ready at {ledger.dir}; commit it with the project")


def cmd_approve(args: argparse.Namespace) -> None:
    ledger = Ledger.at()
    with ledger.lock():
        order = ledger.order(args.order)
        if order["state"] != "drafted":
            raise StError(f"{order['id']} is {order['state']}; only drafted orders are approved")
        level = args.level or order["spec"]["authority"]
        if level not in LEVELS:
            raise StError("approval level must be L0, L1 or L2")
        if args.push and level != "L2":
            raise StError("a push can only be approved at L2")
        if LEVELS[level] < LEVELS[order["spec"]["authority"]]:
            print(
                f"note: approving below the drafted {order['spec']['authority']}; check that "
                "the acceptance criteria are still achievable",
                file=sys.stderr,
            )
        minutes = args.valid_for or max(60, 3 * order["spec"]["budget"]["minutes"])
        not_after = iso(now() + dt.timedelta(minutes=minutes))
        order["approval"] = sign(
            {
                "kind": "approve",
                "order": order["id"],
                "spec_sha": sha(order["spec"]),
                "authority": level,
                "push": bool(args.push),
                "at": iso(now()),
                "not_after": not_after,
            }
        )
        transition(
            ledger,
            order,
            "approved",
            note=f"{level}{' +push' if args.push else ''}",
            by="surgeon",
        )
        ledger.save_order(order)
        render_status(ledger)
    print(
        f"{order['id']} approved at {level}{' with push' if args.push else ''}, "
        f"valid until {not_after}"
    )


def _verdict(args: argparse.Namespace, verdict: State) -> None:
    ledger = Ledger.at()
    with ledger.lock():
        for wo in args.orders:
            order = ledger.order(wo)
            if order["state"] not in ("reported", "deferred"):
                raise StError(f"{wo} is {order['state']}; verdicts apply to reported orders")
            report = ledger.attempt_record("reports", wo, order["attempt"])
            checks = ledger.attempt_record("checks", wo, order["attempt"])
            if verdict == "accepted":
                if (
                    any(
                        "check" in criterion
                        for criterion in order["spec"]["acceptance"]
                    )
                    and not checks
                ):
                    print(
                        f"warning: {wo} has executable checks that were never run (st check {wo})",
                        file=sys.stderr,
                    )
                elif checks and not all(
                    result["ok"] is not False for result in checks["runs"][-1]["results"]
                ):
                    print(f"warning: {wo}: the last check run FAILED", file=sys.stderr)
            payload: JSON = {
                "kind": "verdict",
                "order": wo,
                "attempt": order["attempt"],
                "verdict": verdict,
                "report_sha": sha(report) if report else None,
                "note": args.message or "",
                "at": iso(now()),
            }
            ledger._write(
                ledger.attempt_path("verdicts", wo, order["attempt"]),
                {"order": wo, "attempt": order["attempt"], "signed": sign(payload)},
            )
            Leases(ledger.root).close(wo, "verdict")
            transition(ledger, order, verdict, note=args.message or "", by="surgeon")
            ledger.save_order(order)
            print(f"{wo}: {verdict}")
            if verdict in TERMINAL:
                _release(ledger, wo)
        render_status(ledger)


def cmd_cancel(args: argparse.Namespace) -> None:
    ledger = Ledger.at()
    with ledger.lock():
        order = ledger.order(args.order)
        order["cancellation"] = sign(
            {
                "kind": "cancel",
                "order": order["id"],
                "reason": args.message or "",
                "at": iso(now()),
            }
        )
        Leases(ledger.root).close(order["id"], "cancelled")
        transition(ledger, order, "cancelled", note=args.message or "", by="surgeon")
        ledger.save_order(order)
        render_status(ledger)
    print(f"{order['id']}: cancelled")
    _release(ledger, order["id"])


def _release(ledger: Ledger, wo: str) -> None:
    """A closed order's clean worktree goes; a failure here never undoes the verdict."""
    try:
        message = release_workspace(ledger, wo)
    except StError as error:
        message = f"could not remove the workspace ({error}); `st prune` retries"
    if message:
        print(f"{wo}: {message}")


def _file_decision(ledger: Ledger, payload: JSON) -> str:
    with ledger.lock():
        decision = ledger.next_decision_id()
        payload = {**payload, "id": decision, "at": iso(now())}
        ledger._write(
            ledger.dir / "decisions" / f"{decision}.json",
            {"id": decision, "signed": sign(payload)},
        )
        ledger.event("decided", decision=decision, kind=payload["kind"])
        render_status(ledger)
    return decision


def cmd_decide(args: argparse.Namespace) -> None:
    ledger = Ledger.at()
    ledger.require()
    if args.supersedes:
        status, _ = decision_status(ledger, args.supersedes)
        if status != "active":
            raise StError(f"{args.supersedes} is {status}; only active decisions are superseded")
    decision = _file_decision(
        ledger,
        {
            "kind": "decision",
            "title": args.title,
            "decision": args.decision,
            "why": args.why or "",
            "consequences": args.consequence or [],
            "alternatives": args.rejected or [],
            "scope": args.scope or "",
            "context": args.context or "",
            "supersedes": args.supersedes,
            "expires": args.expires,
            # Pushback the surgeon heard and overruled, signed with the decision.
            "dissent": getattr(args, "dissent", None) or [],
        },
    )
    print(decision)


def cmd_grant(args: argparse.Namespace) -> None:
    ledger = Ledger.at()
    ledger.require()
    if args.max not in LEVELS:
        raise StError("a standing order grants at most L2, never L3")
    if args.role != "*" and not is_role(args.role):
        raise StError(f"unknown role {args.role}")
    if args.expires:
        dt.date.fromisoformat(args.expires)
    decision = _file_decision(
        ledger,
        {
            "kind": "standing",
            "role": args.role,
            "max_authority": args.max,
            "budget_minutes": args.budget,
            "scope": args.scope,
            "expires": args.expires,
            "title": f"Standing order: {args.role} up to {args.max}",
        },
    )
    print(decision)


def cmd_revoke(args: argparse.Namespace) -> None:
    ledger = Ledger.at()
    ledger.require()
    status, _ = decision_status(ledger, args.decision)
    if status != "active":
        raise StError(f"{args.decision} is {status}")
    decision = _file_decision(
        ledger,
        {
            "kind": "revoke",
            "target": args.decision,
            "reason": args.message or "",
            "title": f"Revoke {args.decision}",
        },
    )
    print(decision)
