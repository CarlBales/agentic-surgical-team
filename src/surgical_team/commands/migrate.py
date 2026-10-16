"""st migrate: upgrade a ledger to the current on-disk format (M-3)."""
from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from pathlib import Path

from ..ledger import FORMAT, RECORD_DIRS, Ledger, write_format
from ..model import StError
from ..status import render_status
from ..types import JSON


def _records(ledger: Ledger) -> list[Path]:
    return [p for d in RECORD_DIRS for p in sorted((ledger.dir / d).glob("*.json"))]


def migrate_0_to_1(ledger: Ledger, apply: bool) -> list[str]:
    """Format 0 -> 1: mark every record and write format.json.

    No content changes: specs keep their hashes, so approvals stay valid.
    Approvals signed before v0.3 carry no expiry and stay unhonored; that
    needs the surgeon's signature, which a migration cannot supply.
    """
    notes: list[str] = []
    for path in _records(ledger):
        rec: JSON = json.loads(path.read_text())
        if rec.get("format") == 1:
            continue
        notes.append(f"mark {path.relative_to(ledger.dir)} format 1")
        if path.parent.name == "orders":
            appr = rec.get("approval") or {}
            if appr and not (appr.get("payload") or {}).get("not_after"):
                notes.append(f"  {rec.get('id')}: approval has no expiry (pre-0.3); "
                             "it stays unhonored until you re-approve")
        if apply:
            ledger._write(path, rec)  # _write adds the current format marker
    notes.append("write format.json (format 1)")
    if apply:
        write_format(ledger)
    return notes


MIGRATIONS: dict[int, Callable[[Ledger, bool], list[str]]] = {0: migrate_0_to_1}


def cmd_migrate(args: argparse.Namespace) -> None:
    ledger = Ledger.at()
    with ledger.lock(migrating=True):
        fmt = ledger.format()
        if fmt == FORMAT:
            print(f"ledger is already format {FORMAT}; nothing to do")
            return
        if not isinstance(fmt, int) or fmt not in MIGRATIONS:
            raise StError(f"no migration from ledger format {fmt!r}")
        notes: list[str] = []
        while isinstance(fmt, int) and fmt < FORMAT:
            notes += [f"format {fmt} -> {fmt + 1}"] + MIGRATIONS[fmt](ledger, not args.dry_run)
            fmt += 1
        if not args.dry_run:
            ledger.event("migrated", to=FORMAT)
    print("\n".join(notes))
    if args.dry_run:
        print("dry run: nothing written")
    else:
        render_status(ledger)
        print(f"ledger is now format {FORMAT}; commit .surgical-team/")
