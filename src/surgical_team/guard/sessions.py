"""Which team role a Cursor conversation is (X-1, Cursor host).

Cursor runs one global hook for every conversation, so the role cannot be
an argument as it is on Kiro. Only the guard writes these records, under the
trust root (config_dir(), guard-protected):

  sessions/<conversation>.json  a top-level conversation in a ledger project
                                (sessionStart), including whether its window was
                                rooted in an order workspace
  pending/<id>.json             a Task the guard allowed the copilot to launch:
                                role, order, and the exact prompt; or a plain
                                chat's Task, whose subagent binds as plain
  claimed/<id>.json             a pending dispatch consumed by one conversation
  bindings/<conversation>.json  the role a conversation was bound to, or a
                                persistent refusal for a top-level workspace chat

A subagent's first tool call claims the uniquely longest pending dispatch
whose prompt appears in its transcript opening. A claim is a rename, so one
dispatch binds one conversation. Equally specific matches bind nothing unless
they are the same briefing launched again, which claims the oldest. A
binding grants nothing by itself: authority still comes from the order's
lease and the surgeon's signatures.

Cleanup runs only when an interactive team session starts, keeping ordinary
guard calls cheap. Pending and claimed dispatch records expire after one hour;
session and binding records expire after 14 days since their last write. A
binding's mtime is refreshed whenever it resolves a tool call, so an active
long-running conversation is retained. If cleanup prunes a copilot binding,
the retained session record can restore only the copilot role. A specialist
has no session record and is refused after its binding and consumed dispatch
have aged out; cleanup never infers a replacement role.
"""
from __future__ import annotations

import contextlib
import json
import math
import os
import re
import time
import uuid
from pathlib import Path

from ..signing import config_dir
from ..types import JSON

PLAIN = "plain"  # a non-team chat in a ledger project, or its subagent; never a team role
PENDING_TTL_S = 60 * 60
STATE_RETENTION_S = 14 * 24 * 60 * 60
CONVERSATION_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


def store() -> Path:
    return config_dir() / "cursor"


def valid_conversation(conversation: object) -> bool:
    return isinstance(conversation, str) and bool(CONVERSATION_RE.match(conversation))


def _write(path: Path, record: JSON) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}")
    tmp.write_text(json.dumps(record) + "\n")
    os.replace(tmp, path)


def _read(path: Path) -> JSON | None:
    try:
        record = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    return record if isinstance(record, dict) else None


def _pending_expired(record: JSON | None, now: float) -> bool:
    if record is None:
        return True
    try:
        at = float(record.get("at", 0))
    except (TypeError, ValueError, OverflowError):
        return True
    return not math.isfinite(at) or now - at > PENDING_TTL_S


def _at(record: JSON) -> float:
    try:
        return float(record.get("at", 0))
    except (TypeError, ValueError, OverflowError):
        return 0.0


def _live_pending(now: float) -> list[tuple[Path, JSON]]:
    """Read every live pending record and discard expired or malformed ones."""
    pending = store() / "pending"
    if not pending.is_dir():
        return []
    live: list[tuple[Path, JSON]] = []
    for path in sorted(pending.glob("*.json")):
        record = _read(path)
        if _pending_expired(record, now):
            with contextlib.suppress(OSError):
                path.unlink()
        elif record is not None:
            live.append((path, record))
    return live


def _prune_older_than(directory: Path, now: float, max_age_s: float) -> None:
    if not directory.is_dir():
        return
    for path in sorted(directory.glob("*.json")):
        try:
            if now - path.stat().st_mtime > max_age_s:
                path.unlink()
        except OSError:
            continue  # another hook may have removed or replaced the record


def cleanup() -> None:
    """Opportunistically bound Cursor state; called only on team sessionStart."""
    now = time.time()
    _live_pending(now)
    root = store()
    _prune_older_than(root / "claimed", now, PENDING_TTL_S)
    _prune_older_than(root / "sessions", now, STATE_RETENTION_S)
    _prune_older_than(root / "bindings", now, STATE_RETENTION_S)


def mark_session(conversation: str, project: str, *, workspace: bool = False) -> None:
    cleanup()
    _write(store() / "sessions" / f"{conversation}.json", {
        "conversation": conversation,
        "project": project,
        "workspace": workspace,
        "at": time.time(),
    })


def session_record(conversation: str) -> JSON | None:
    return _read(store() / "sessions" / f"{conversation}.json")


def session_seen(conversation: str) -> bool:
    return (store() / "sessions" / f"{conversation}.json").is_file()


def binding(conversation: str) -> JSON | None:
    path = store() / "bindings" / f"{conversation}.json"
    record = _read(path)
    if record is not None:
        with contextlib.suppress(OSError):
            os.utime(path)
    return record


def bind(conversation: str, role: str, **extra: object) -> JSON:
    record: JSON = {"conversation": conversation, "role": role, "at": time.time(), **extra}
    _write(store() / "bindings" / f"{conversation}.json", record)
    return record


def add_pending(prompt: str, role: str, wo: str | None, parent: str) -> None:
    _write(store() / "pending" / f"{uuid.uuid4().hex}.json",
           {"prompt": prompt, "role": role, "wo": wo, "parent": parent, "at": time.time()})


def has_pending_dispatch() -> bool:
    """Whether a live Task dispatch is still waiting for its subagent."""
    return bool(_live_pending(time.time()))


def claim(conversation: str, opening: str) -> JSON | None:
    """Bind `conversation` to its unique, most-specific pending dispatch."""
    if not opening:
        return None
    matches: list[tuple[int, Path, JSON]] = []
    for path, record in _live_pending(time.time()):
        prompt = str(record.get("prompt") or "").strip()
        if prompt and prompt in opening:
            matches.append((len(prompt), path, record))
    if not matches:
        return None
    longest = max(length for length, _path, _record in matches)
    specific = [match for match in matches if match[0] == longest]
    # Re-launching the same briefing leaves identical records: one order, one
    # role, so they are one candidate and the oldest is claimed first. Distinct
    # prompts of equal length are ambiguous; fail closed instead of guessing.
    candidates = {(str(r.get("prompt", "")).strip(), r.get("role"), r.get("wo"))
                  for _length, _path, r in specific}
    if len(candidates) != 1:
        return None
    _length, path, record = min(specific, key=lambda match: (_at(match[2]), match[1].name))
    claimed = store() / "claimed" / path.name
    claimed.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.rename(path, claimed)
    except FileNotFoundError:  # another conversation claimed it first
        return None
    with contextlib.suppress(OSError):
        os.utime(claimed)  # claimed retention starts when the dispatch is consumed
    return bind(conversation, str(record["role"]), wo=record.get("wo"),
                parent=record.get("parent"), dispatch=path.stem)
