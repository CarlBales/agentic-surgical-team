"""Who holds authority right now: decisions, approvals, standing orders, leases."""
from __future__ import annotations

import contextlib
import datetime as dt
import json
from typing import Literal, cast

from .ledger import READABLE_FORMATS, Leases, Ledger, grant_id
from .model import LEVELS, TERMINAL, StError, now, parse_iso, sha
from .signing import verify
from .types import JSON, LeaseEvent, Order

DecisionStatus = Literal[
    "active", "superseded", "revoked", "expired", "unverified", "missing"
]
LiveOrder = tuple[Order, LeaseEvent, int, bool]


def live_orders(
    ledger: Ledger, role: str | None = None, only: str | None = None
) -> list[LiveOrder]:
    """Orders with authority right now: (order, lease, level, push).

    Derived from the local lease store and signatures only. The ledger
    supplies the spec, which must match what the lease and grant bound.

    With `role`, only leases bound to that role are considered (P-1): the
    lease records the role it was opened for, and an order whose spec role
    differs from its lease is skipped below anyway, so filtering first
    changes which signatures are verified, never which orders are live.
    `only` restricts the same way to one order ID.
    """
    active: list[LiveOrder] = []
    if ledger.format() not in READABLE_FORMATS:
        return active  # a format this build cannot read grants nothing (M-3)
    current_time = now()
    for wo, lease in Leases(ledger.root).open_leases().items():
        if role is not None and lease.get("role") != role:
            continue
        if only is not None and wo != only:
            continue
        with contextlib.suppress(StError, OSError, json.JSONDecodeError, KeyError):
            order = ledger.order(wo)
            if sha(order["spec"]) != lease.get("spec_sha") or grant_id(order) != lease.get(
                "grant"
            ):
                continue
            if order["spec"]["role"] != lease.get("role"):
                continue
            not_after = lease.get("not_after")
            if not_after and current_time > parse_iso(not_after):
                continue
            level, push, _ = effective_authority(ledger, order)
            if level is None:
                continue
            if verdict_for(ledger, order, lease["attempt"]) in ("accepted", "rejected"):
                continue
            active.append((order, lease, level, push))
    return active


def decision_status(ledger: Ledger, dec_id: str) -> tuple[DecisionStatus, JSON | None]:
    """Return ('active'|'superseded'|'revoked'|'expired'|'unverified'|'missing', record)."""
    record = ledger.decision(dec_id)
    if not record:
        return "missing", None
    ok, _ = verify(record.get("signed"), {"id": dec_id})
    if not ok:
        return "unverified", record
    for other in ledger.decisions():
        # P-1: read the unsigned payload first and verify only records that
        # would end this decision. An unverified revocation still counts for
        # nothing, so this changes the cost, not the answer.
        signed = other.get("signed")
        payload = signed.get("payload") if isinstance(signed, dict) else None
        if not isinstance(payload, dict):
            continue
        if payload.get("kind") == "revoke" and payload.get("target") == dec_id:
            if verify(signed)[0]:
                return "revoked", record
        elif payload.get("supersedes") == dec_id:
            if verify(signed)[0]:
                return "superseded", record
    expires = record["signed"]["payload"].get("expires")
    if expires and now().date() > dt.date.fromisoformat(expires):
        return "expired", record
    return "active", record


def effective_authority(ledger: Ledger, order: Order) -> tuple[int | None, bool, str]:
    """(level, push_permitted, source-or-reason). level None means no authority."""
    spec = order["spec"]
    approval = order.get("approval")
    if approval:
        ok, why = verify(
            approval,
            {"kind": "approve", "order": order["id"], "spec_sha": sha(spec)},
        )
        if not ok:
            return None, False, f"approval {why}"
        payload = approval["payload"]
        if not payload.get("not_after"):
            return None, False, "approval has no expiry (pre-0.3); the surgeon re-approves"
        if now() > parse_iso(payload["not_after"]):
            return None, False, f"approval expired at {payload['not_after']}"
        return LEVELS[payload["authority"]], bool(payload.get("push")), "approval"
    dec_id = spec.get("standing")
    if dec_id:
        status, record = decision_status(ledger, dec_id)
        if status != "active":
            return None, False, f"standing order {dec_id} is {status}"
        if record is None:
            # An active status must carry a record. Treat an inconsistent result
            # as no authority rather than dereferencing None and relying on the
            # outer guard exception handler to fail closed.
            return None, False, f"standing order {dec_id} has no record"
        payload = record["signed"]["payload"]
        if payload.get("kind") != "standing":
            return None, False, f"{dec_id} is not a standing order"
        if payload["role"] not in ("*", spec["role"]):
            return None, False, f"{dec_id} does not cover role {spec['role']}"
        if LEVELS[spec["authority"]] > LEVELS[payload["max_authority"]]:
            return None, False, f"{dec_id} allows at most {payload['max_authority']}"
        if spec.get("push"):
            return None, False, "standing orders never permit a push"
        ceiling = payload.get("budget_minutes")
        if ceiling and spec["budget"]["minutes"] > ceiling:
            return None, False, f"{dec_id} budget ceiling is {ceiling}m"
        return LEVELS[spec["authority"]], False, f"standing {dec_id}"
    return None, False, "not approved"


def verdict_for(ledger: Ledger, order: Order, attempt: int | None = None) -> str | None:
    attempt = attempt or order.get("attempt", 0)
    record = ledger.attempt_record("verdicts", order["id"], attempt)
    if not record:
        return None
    ok, _ = verify(
        record.get("signed"),
        {"kind": "verdict", "order": order["id"], "attempt": attempt},
    )
    if not ok:
        return "unverified"
    # Verified verdict payloads are produced by _verdict with a string value.
    return cast(str, record["signed"]["payload"]["verdict"])


def integrity_problems(ledger: Ledger) -> list[str]:
    problems: list[str] = []
    for order in ledger.orders():
        if order.get("approval"):
            ok, why = verify(
                order["approval"],
                {"kind": "approve", "order": order["id"], "spec_sha": sha(order["spec"])},
            )
            if not ok:
                problems.append(f"{order['id']}: approval {why}")
        elif order["state"] == "approved":
            problems.append(f"{order['id']}: state approved with no approval record")
        if order["state"] in ("accepted", "rejected"):
            verdict = verdict_for(ledger, order)
            if verdict != order["state"]:
                problems.append(
                    f"{order['id']}: state {order['state']} but verified verdict is {verdict}"
                )
        if order["state"] == "cancelled":
            ok, _ = verify(
                order.get("cancellation"), {"kind": "cancel", "order": order["id"]}
            )
            if not ok:
                problems.append(f"{order['id']}: cancelled without a verified cancellation")
        if order["state"] == "dispatched" and (
            ledger.attempt_record("reports", order["id"], order.get("attempt", 0))
            or ledger.attempt_record("verdicts", order["id"], order.get("attempt", 0))
        ):
            problems.append(
                f"{order['id']}: state dispatched but attempt {order.get('attempt')} was "
                "already reported (state rolled back?)"
            )
        for attempt in range(1, order.get("attempt", 0) + 1):
            verdict = verdict_for(ledger, order, attempt)
            if verdict in ("accepted", "rejected") and order["state"] not in TERMINAL:
                problems.append(
                    f"{order['id']}: signed verdict {verdict} on attempt {attempt} "
                    f"but state is {order['state']}"
                )
    for decision in ledger.decisions():
        ok, why = verify(decision.get("signed"), {"id": decision.get("id")})
        if not ok:
            problems.append(f"{decision.get('id')}: {why}")
    return problems
