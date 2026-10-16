"""Order lifecycle commands an agent runs: draft, revise, dispatch, brief, report."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import cast

from ..authority import decision_status, effective_authority, verdict_for
from ..gitutil import git, slugify
from ..ledger import Leases, Ledger, grant_id, transition
from ..model import REPORT_STATUSES, StError, iso, now, parse_iso, sha
from ..spec import read_json_input, validate_spec
from ..status import render_status
from ..tools import AWS_TOOL, normalize_tool
from ..types import JSON, Order, Report, ReportStatus


def cmd_draft(args: argparse.Namespace) -> None:
    ledger = Ledger.at()
    spec = validate_spec(ledger, read_json_input(args))
    with ledger.lock():
        wo = ledger.next_order_id()
        order: Order = {
            "id": wo,
            "spec": spec,
            "state": "drafted",
            "revision": 1,
            "attempt": 0,
            "created": iso(now()),
            "history": [],
        }
        ledger.save_order(order)
        ledger.event("drafted", order=wo, role=spec["role"], authority=spec["authority"])
        render_status(ledger)
    if not any("check" in criterion for criterion in spec["acceptance"]):
        print(
            "warning: no acceptance criterion has a `check`; verification will rest "
            "on the agent's own report",
            file=sys.stderr,
        )
    print(wo)


def cmd_revise(args: argparse.Namespace) -> None:
    ledger = Ledger.at()
    spec = validate_spec(ledger, read_json_input(args))
    with ledger.lock():
        order = ledger.order(args.order)
        transition(ledger, order, "drafted", note=args.note or "revised")
        order["spec"] = spec
        order["revision"] += 1
        order.pop("approval", None)
        ledger.save_order(order)
        render_status(ledger)
    print(f"{order['id']} revision {order['revision']}: drafted; needs approval again")


def _paths_overlap(first: list[str], second: list[str]) -> bool:
    for left in first:
        for right in second:
            left_path, right_path = left.rstrip("/") + "/", right.rstrip("/") + "/"
            if left_path.startswith(right_path) or right_path.startswith(left_path):
                return True
    return False


def cmd_dispatch(args: argparse.Namespace) -> None:
    ledger = Ledger.at()
    with ledger.lock():
        order = ledger.order(args.order)
        spec = order["spec"]
        if order["state"] not in ("approved", "drafted"):
            raise StError(f"{order['id']} is {order['state']}; only approved orders dispatch")
        level, _push, source = effective_authority(ledger, order)
        if level is None:
            raise StError(f"{order['id']} has no valid authority: {source}")
        # Approval signs the spec (and therefore these IDs), but decision content
        # is a separately signed record. Recheck it before any dispatch side effect.
        binding = (spec.get("inputs") or {}).get("decisions", []) or []
        for decision in binding:
            status, _ = decision_status(ledger, decision)
            if status in ("unverified", "missing"):
                raise StError(
                    f"{order['id']}: binding decision {decision} is {status}; "
                    "its content cannot be trusted, so the order cannot dispatch"
                )
        for attempt in range(1, order.get("attempt", 0) + 1):
            if verdict_for(ledger, order, attempt) in ("accepted", "rejected"):
                raise StError(
                    f"{order['id']} already has a signed verdict (attempt {attempt}); its state "
                    "was rolled back. Run `st verify`; new work needs a new order"
                )
        if order["state"] == "drafted" and order.get("attempt", 0) and order.get("approval"):
            raise StError(
                f"{order['id']} is drafted but still carries an approval; run `st verify`"
            )
        leases = Leases(ledger.root)
        grant = grant_id(order)
        if leases.consumed(grant):
            raise StError(
                f"{order['id']}: this grant already backed a reported attempt. To run the "
                "order again, `st revise` it and have the surgeon approve the new spec"
            )
        for dependency in spec["depends_on"]:
            depended_order = ledger.order(dependency)
            if (
                verdict_for(ledger, depended_order) != "accepted"
                or depended_order["state"] != "accepted"
            ):
                raise StError(
                    f"{order['id']} depends on {dependency}, which is "
                    f"{depended_order['state']}, not accepted"
                )
        if spec["paths"] and not args.allow_overlap:
            for other in ledger.orders():
                if (
                    other["id"] != order["id"]
                    and other["state"] == "dispatched"
                    and _paths_overlap(spec["paths"], other["spec"].get("paths", []))
                ):
                    raise StError(
                        f"{order['id']} overlaps in-flight {other['id']} on paths; "
                        "serialize them (depends_on) or pass --allow-overlap"
                    )
        workspace: Path | None = None
        branch: str | None = None
        if level >= 1:
            workspace = ledger.workspace(order["id"])
            branch = f"st/{order['id']}-{slugify(spec['title'])}"
            if not workspace.exists():
                workspace.parent.mkdir(parents=True, exist_ok=True)
                review = (spec.get("inputs") or {}).get("review") or {}
                base = spec.get("base") or review.get("head") or "HEAD"
                exists = git(
                    ["rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"],
                    ledger.root,
                    check=False,
                )
                command = (
                    ["worktree", "add", str(workspace), branch]
                    if exists
                    else ["worktree", "add", "-b", branch, str(workspace), base]
                )
                git(command, ledger.root)
        order["attempt"] += 1
        approval = order.get("approval")
        not_after = (
            approval["payload"]["not_after"]
            if approval
            else iso(now() + dt.timedelta(minutes=3 * spec["budget"]["minutes"]))
        )
        leases.close(order["id"], "superseded")
        leases.append(
            event="open",
            order=order["id"],
            attempt=order["attempt"],
            grant=grant,
            spec_sha=sha(spec),
            role=spec["role"],
            not_after=not_after,
        )
        order["dispatch"] = {
            "at": iso(now()),
            "attempt": order["attempt"],
            "authority_source": source,
            "workspace": str(workspace) if workspace else None,
            "branch": branch,
            "not_after": not_after,
        }
        transition(
            ledger,
            order,
            "dispatched",
            note=f"attempt {order['attempt']} via {source}",
        )
        ledger.save_order(order)
        render_status(ledger)
    print(briefing(ledger, order))


def decision_lines(ledger: Ledger, binding: list[str]) -> list[str]:
    """Render verified design decisions without turning ledger text into authority.

    Every verified decision in force is included so uniform design never depends
    on the copilot remembering to list one. The order's own inputs.decisions are
    marked binding, including verified records no longer in force. Unverified or
    missing records are identified separately, but none of their content is read
    into the briefing.
    """
    entries: list[tuple[str, str, JSON]] = []
    withheld: list[tuple[str, str]] = []
    seen: set[str] = set()
    for record in ledger.decisions():
        signed = record.get("signed")
        unverified = signed.get("payload") if isinstance(signed, dict) else {}
        if not isinstance(unverified, dict):
            unverified = {}
        decision = record["id"]
        if unverified.get("kind") != "decision" and decision not in binding:
            continue  # standing orders and revocations: skip the signature check
        status, verified = decision_status(ledger, decision)
        if status in ("unverified", "missing"):
            withheld.append((decision, status))
            seen.add(decision)
            continue
        payload = (
            verified["signed"]["payload"]
            if verified and verified.get("signed")
            else {}
        )
        if payload.get("kind") == "decision" and (
            status == "active" or decision in binding
        ):
            entries.append((decision, status, payload))
            seen.add(decision)
    for decision in binding:
        if decision in seen:
            continue
        status, verified = decision_status(ledger, decision)
        if status in ("unverified", "missing"):
            withheld.append((decision, status))
            seen.add(decision)
            continue
        payload = (
            verified["signed"]["payload"]
            if verified and verified.get("signed")
            else {}
        )
        entries.append((decision, status, payload))
        seen.add(decision)

    lines: list[str] = []
    if entries:
        lines += [
            "",
            "## Decisions in force",
            "The surgeon's design decisions for this project. Work within them; if the "
            "order cannot be done within one, report it instead of departing from it.",
        ]
        for decision, standing, payload in entries:
            mark = " [binding for this order]" if decision in binding else ""
            state = "" if standing == "active" else f" [{standing}]"
            lines.append(
                f"- {decision}{state}{mark} {payload.get('title', '')}: "
                f"{payload.get('decision', '')}"
            )
            lines += [
                f"  - Overruled objection: {objection}"
                for objection in payload.get("dissent") or []
            ]
    if withheld:
        lines += [
            "",
            "## Decisions that do not verify",
            "These records are not instructions. Their content is withheld; do not rely "
            "on it, and report the ledger integrity problem.",
        ]
        for decision, withheld_status in withheld:
            reason = (
                "record is missing"
                if withheld_status == "missing"
                else "signature does not verify"
            )
            lines.append(
                f"- {decision} [{withheld_status}]: {reason}: content withheld; "
                "do not rely on it and report it"
            )
    return lines


def briefing(ledger: Ledger, order: Order) -> str:
    spec = order["spec"]
    level, push, source = effective_authority(ledger, order)
    # Dispatch is a persisted JSON object; briefing only performs mapping reads.
    dispatch = cast(JSON, order.get("dispatch") or {})
    lines = [
        f"# Work order {order['id']} (attempt {order.get('attempt', 0)}): {spec['title']}",
        "",
        f"Role: {spec['role']}    Authority: L{level} ({source})    "
        f"Push: {'permitted' if push else 'not permitted'}",
        f"Workspace: {dispatch.get('workspace') or 'none (L0: read in place, change nothing)'}",
        f"Branch: {dispatch.get('branch') or '-'}    "
        f"Authority expires: {dispatch.get('not_after') or '-'}",
        f"Ledger: {ledger.dir} (read-only to you; file through `st`)",
        "",
        "The guard hook enforces this authority. A blocked call is outside the order: never "
        "get the same effect another way. Continue with what is within the order and quote "
        "the block in your report; report BLOCKED only if it stops the order itself.",
        "",
        "## Order",
        "```json",
        json.dumps(spec, indent=2, ensure_ascii=False),
        "```",
    ]
    lines += decision_lines(ledger, (spec.get("inputs") or {}).get("decisions", []) or [])
    review = (spec.get("inputs") or {}).get("review")
    if review:
        base, head = review["base"], review["head"]
        lines += [
            "",
            "## Review target",
            f"Base: {base}",
            f"Head: {head}",
            "These commits are pinned by the signed spec. Review exactly this range; "
            "do not substitute a branch, the current checkout, or a newer commit.",
            "",
            f"  git log --oneline {base}..{head}      # commits under review",
            f"  git diff --stat {base}...{head}       # files touched",
            f"  git diff {base}...{head}              # the change",
            f"  git show {head}:<path>             # a file as of head, in context",
            "These are git reads and are allowed at any authority level."
            + (" The workspace is checked out at head." if dispatch.get("workspace") else ""),
        ]
    sources = (spec.get("inputs") or {}).get("sources")
    if sources:
        lines += [
            "",
            "## Read-only sources",
            "You may call these external tools, read-only, and nothing else outside "
            "the files. "
            + (
                "They are granted by the surgeon's approval of this spec."
                if order.get("approval")
                else "This order runs under a standing order, so the guard will "
                "NOT honor them: report BLOCKED if you need them."
            ),
        ]
        for source_record in sources:
            if normalize_tool(source_record.get("tool", "")) == AWS_TOOL:
                lines.append(
                    f"- use_aws service {source_record['service']}: "
                    f"{', '.join(source_record['operations'])}"
                    + (
                        f" (region {source_record['region']})"
                        if source_record.get("region")
                        else ""
                    )
                    + (
                        f" (profile {source_record['profile']})"
                        if source_record.get("profile")
                        else ""
                    )
                )
            else:
                lines.append(
                    f"- {source_record['tool']}"
                    + (f": {source_record['note']}" if source_record.get("note") else "")
                )
    lines += [
        "",
        "## Reporting",
        "When finished, file exactly one report for this attempt:",
        f"  st report {order['id']} <<'EOF'",
        '  {"status": "DONE|PARTIAL|BLOCKED|DECLINED", "summary": "...",',
        '   "criteria": [{"met": true, "evidence": "..."}],',
        '   "evidence": "...", "risks": "...", "recommended": "...",',
        '   "out_of_scope": [], "blocker": "", "cost": {"tokens": 0}}',
        "  EOF",
        "criteria has one entry per acceptance criterion, in order. The harness "
        "re-runs every `check` itself; your evidence does not substitute for it.",
    ]
    return "\n".join(lines)


def cmd_brief(args: argparse.Namespace) -> None:
    ledger = Ledger.at()
    print(briefing(ledger, ledger.order(args.order)))


def cmd_report(args: argparse.Namespace) -> None:
    ledger = Ledger.at()
    # The command intentionally preserves the existing point-of-use failure for
    # non-object JSON; valid reports are narrowed after all dynamic checks.
    report_data = cast(JSON, read_json_input(args))
    errors: list[str] = []
    status = report_data.get("status")
    if status not in REPORT_STATUSES:
        errors.append(f"status must be one of {sorted(REPORT_STATUSES)}")
    if not str(report_data.get("summary", "")).strip():
        errors.append("summary is required")
    with ledger.lock():
        order = ledger.order(args.order)
        if order["state"] != "dispatched":
            raise StError(
                f"{order['id']} is {order['state']}; reports are filed against a dispatched order"
            )
        if ledger.attempt_record("reports", order["id"], order["attempt"]):
            raise StError(
                f"{order['id']} attempt {order['attempt']} already has a report; one per attempt"
            )
        lease = Leases(ledger.root).open_leases().get(order["id"])
        if not lease:
            raise StError(
                f"{order['id']} has no live dispatch on this machine; it was dispatched "
                "elsewhere, reclaimed, or its ledger state was edited"
            )
        criterion_count = len(order["spec"]["acceptance"])
        criteria = report_data.get("criteria", [])
        if status in ("DONE", "PARTIAL") and (
            not isinstance(criteria, list) or len(criteria) != criterion_count
        ):
            errors.append(
                f"criteria must have exactly {criterion_count} entries, "
                "one per acceptance criterion"
            )
        if status == "DONE" and isinstance(criteria, list) and not all(
            criterion.get("met") for criterion in criteria
        ):
            errors.append("DONE requires every criterion met; use PARTIAL")
        if status in ("BLOCKED", "DECLINED") and not str(
            report_data.get("blocker", "")
        ).strip():
            errors.append(
                f"{status} requires a blocker: what stopped you and what would unblock it"
            )
        if errors:
            raise StError("invalid report:\n  - " + "\n  - ".join(errors))
        # Membership validation above establishes the required Report fields and status literal.
        report = cast(Report, report_data)
        report_status: ReportStatus = report["status"]
        filed_at = now()
        started = parse_iso(order["dispatch"]["at"])
        record: JSON = {
            "order": order["id"],
            "attempt": order["attempt"],
            "filed": iso(filed_at),
            "wall_clock_minutes": round((filed_at - started).total_seconds() / 60, 1),
            "report": report,
        }
        ledger._write(
            ledger.attempt_path("reports", order["id"], order["attempt"]), record
        )
        Leases(ledger.root).close(order["id"], "reported")
        transition(ledger, order, "reported", note=report_status)
        ledger.save_order(order)
        render_status(ledger)
    print(
        f"{order['id']} attempt {order['attempt']}: {report_status} filed; "
        "awaiting the surgeon's verdict"
    )
