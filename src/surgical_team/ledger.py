"""The ledger (.surgical-team/) and the lease store outside the repository."""
from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import cast

from .gitutil import git, in_git_checkout, repo_root
from .model import LEDGER_DIRNAME, TRANSITIONS, WO_RE, StError, iso, now, sha
from .signing import config_dir
from .types import JSON, LeaseEvent, Order, State


# M-3: the ledger's on-disk format. Records carry "format": FORMAT and the
# ledger has format.json. Format 0 is any ledger from before v0.5 (no markers).
# st reads every format in READABLE_FORMATS but writes only FORMAT; `st
# migrate` upgrades. A format newer than this build understands is refused,
# and the guard grants no authority from it (fail closed).
FORMAT = 1
READABLE_FORMATS = (0, 1)
RECORD_DIRS = ("orders", "reports", "checks", "verdicts", "decisions")


class Ledger:
    SUBDIRS = ("orders", "reports", "checks", "verdicts", "decisions", "journal")

    def __init__(self, root: Path) -> None:
        self.root = root
        self.dir = root / LEDGER_DIRNAME
        self._migrating = False

    @classmethod
    def at(cls, cwd: str | Path | None = None) -> Ledger:
        return cls(repo_root(cwd or os.getcwd()))

    def exists(self) -> bool:
        return (self.dir / "orders").is_dir()

    def require(self) -> None:
        if not self.exists():
            raise StError(f"no ledger at {self.dir}; the surgeon runs: st init")
        fmt = self.format()
        if fmt not in READABLE_FORMATS:
            raise StError(f"ledger format {fmt!r} is newer than this st understands "
                          f"(reads {', '.join(map(str, READABLE_FORMATS))}); upgrade st")

    def format(self) -> object:
        """The ledger's format: 0 if it predates format.json; whatever it says otherwise."""
        path = self.dir / "format.json"
        if not path.exists():
            return 0
        try:
            return cast(JSON, json.loads(path.read_text())).get("format")
        except (json.JSONDecodeError, AttributeError):
            return "unreadable"

    def require_writable(self) -> None:
        self.require()
        fmt = self.format()
        if fmt != FORMAT:
            raise StError(f"ledger format {fmt} is older than this st writes ({FORMAT}); "
                          "the surgeon runs: st migrate")

    @contextlib.contextmanager
    def lock(self, migrating: bool = False) -> Iterator[None]:
        """Exclusive lock for a write. Writes need the current format, except migrations."""
        if migrating:
            self.require()
        else:
            self.require_writable()
        with open(self.dir / ".lock", "w") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            self._migrating = migrating
            try:
                yield
            finally:
                self._migrating = False
                fcntl.flock(handle, fcntl.LOCK_UN)

    def workspace(self, wo: str) -> Path:
        return self.root.parent / f"{self.root.name}.st" / wo

    # files
    def _read(self, path: Path) -> JSON:
        # Ledger files written by st are JSON objects; retaining a cast here
        # preserves existing malformed-record failures at their point of use.
        return cast(JSON, json.loads(path.read_text()))

    def _write(self, path: Path, obj: object) -> None:
        if not self._migrating:
            self.require_writable()
        if isinstance(obj, dict) and path.parent.name in RECORD_DIRS:
            obj = {**obj, "format": FORMAT}
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        )
        os.replace(temporary, path)

    def event(self, name: str, **data: object) -> None:
        if not self._migrating:
            self.require_writable()
        with open(self.dir / "events.jsonl", "a") as handle:
            handle.write(
                json.dumps({"at": iso(now()), "event": name, **data}, sort_keys=True) + "\n"
            )

    # orders
    def order_path(self, wo: str) -> Path:
        return self.dir / "orders" / f"{wo}.json"

    def order(self, wo: str) -> Order:
        if not WO_RE.match(wo or ""):
            raise StError(f"not an order ID: {wo!r}")
        path = self.order_path(wo)
        if not path.exists():
            raise StError(f"no such order: {wo}")
        # validate_spec establishes the persisted Order shape before this read.
        return cast(Order, self._read(path))

    def save_order(self, order: Order) -> None:
        self._write(self.order_path(order["id"]), order)

    def orders(self) -> list[Order]:
        records = [self._read(path) for path in sorted((self.dir / "orders").glob("WO-*.json"))]
        # Every file in orders/ is created through save_order from a validated order.
        return cast(list[Order], records)

    def next_order_id(self) -> str:
        day = now().strftime("%Y%m%d")
        nums = [
            int(path.stem[-3:])
            for path in (self.dir / "orders").glob(f"WO-{day}-*.json")
        ]
        number = max(nums, default=0) + 1
        if number > 999:
            raise StError("order numbering exhausted for today")
        return f"WO-{day}-{number:03d}"

    # per-attempt records
    def attempt_path(self, kind: str, wo: str, attempt: int) -> Path:
        return self.dir / kind / f"{wo}.a{attempt}.json"

    def attempt_record(self, kind: str, wo: str, attempt: int) -> JSON | None:
        path = self.attempt_path(kind, wo, attempt)
        return self._read(path) if path.exists() else None

    # decisions
    def decision(self, dec: str) -> JSON | None:
        path = self.dir / "decisions" / f"{dec}.json"
        return self._read(path) if path.exists() else None

    def decisions(self) -> list[JSON]:
        return [
            self._read(path)
            for path in sorted((self.dir / "decisions").glob("DEC-*.json"))
        ]

    def next_decision_id(self) -> str:
        nums = [int(path.stem[4:]) for path in (self.dir / "decisions").glob("DEC-*.json")]
        return f"DEC-{max(nums, default=0) + 1:03d}"


_FOUND: dict[Path, Ledger | None] = {}


def _unsupported_team_root(directory: Path) -> Path | None:
    """A team root above a checkout whose safe filesystem discovery failed.

    The ancestor check keeps this error path from asking Git to interpret an
    agent-writable order-workspace gitfile: those workspaces have no ledger
    ancestor. When a checkout itself contains a ledger, a scrubbed rev-parse
    confirms its top level for legitimate submodule/separate-git-dir layouts.
    Falling back to the nearest ledger ancestor still fails closed if Git
    cannot describe a malformed team checkout.
    """
    candidates = [
        candidate
        for candidate in (directory, *directory.parents)
        if (candidate / LEDGER_DIRNAME).is_dir()
    ]
    if not candidates:
        return None
    try:
        output = git(["rev-parse", "--show-toplevel"], directory, check=False)
        top = Path(output).resolve() if output else None
    except (OSError, RuntimeError, ValueError):
        top = None
    if top is not None and (top / LEDGER_DIRNAME).is_dir():
        return top
    return candidates[0]


def ledger_at(directory: Path) -> Ledger | None:
    """The team ledger of the checkout containing `directory`, if one exists.

    For the guard, which answers one tool call per process and may look up
    several target directories: results are cached until clear_ledger_cache(),
    and a directory outside any git checkout needs no git subprocess at all.
    A checkout with a visible team ledger but an unsupported Git layout raises
    instead of being mistaken for a non-team directory (fail closed).
    """
    if directory not in _FOUND:
        found: Ledger | None = None
        if in_git_checkout(directory):
            try:
                ledger = Ledger.at(directory)
            except (StError, OSError) as error:
                root = _unsupported_team_root(directory)
                if root is not None:
                    raise StError(
                        f"team checkout at {root} uses an unsupported Git layout; "
                        "the guard cannot safely discover its ledger and refuses this "
                        f"tool call ({error})"
                    ) from error
            else:
                if ledger.exists():
                    found = ledger
        _FOUND[directory] = found
    return _FOUND[directory]


def clear_ledger_cache() -> None:
    _FOUND.clear()


def write_format(ledger: Ledger) -> None:
    path = ledger.dir / "format.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"format": FORMAT}, indent=2) + "\n")
    os.replace(tmp, path)


class Leases:
    """Where live authority is recorded: outside the repository.

    The ledger is shared (committed, pulled, merged), so anything in it can
    arrive from someone without the surgeon's key. Leases live in the
    surgeon's config directory, which the guard protects from every agent
    tool, and are append-only: `st dispatch` opens one, and `st report`,
    `reclaim`, `cancel`, and verdicts close it. The guard grants authority
    only for an open lease whose signed grant still verifies, so editing,
    rolling back, or deleting ledger files grants nothing, and a ledger from
    another clone is inert here.
    """

    def __init__(self, root: Path) -> None:
        key = hashlib.sha256(str(root.resolve()).encode()).hexdigest()[:16]
        self.path = config_dir() / "leases" / f"{key}.jsonl"

    def events(self) -> list[LeaseEvent]:
        if not self.path.exists():
            return []
        events: list[LeaseEvent] = []
        for line in self.path.read_text().splitlines():
            with contextlib.suppress(json.JSONDecodeError):
                # append() writes this shape; malformed decoded values retain
                # their previous failure behavior when consumers access them.
                events.append(cast(LeaseEvent, json.loads(line)))
        return events

    def append(self, **event: object) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(self.path.parent, 0o700)
        with open(self.path, "a") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            handle.write(json.dumps({"at": iso(now()), "format": FORMAT, **event},
                                    sort_keys=True) + "\n")
            fcntl.flock(handle, fcntl.LOCK_UN)

    def open_leases(self) -> dict[str, LeaseEvent]:
        """order id -> the open lease record, if any."""
        live: dict[str, LeaseEvent] = {}
        for event in self.events():
            if event.get("event") == "open":
                live[event["order"]] = event
            elif (
                event.get("event") == "close"
                and event["order"] in live
                and live[event["order"]].get("attempt") == event.get("attempt")
            ):
                del live[event["order"]]
        return live

    def consumed(self, grant: str) -> bool:
        """A grant backs at most one reported attempt."""
        return any(
            event.get("event") == "close"
            and event.get("grant") == grant
            and event.get("reason") in ("reported", "verdict", "cancelled")
            for event in self.events()
        )

    def close(self, order: str, reason: str) -> LeaseEvent | None:
        lease = self.open_leases().get(order)
        if lease:
            self.append(
                event="close",
                order=order,
                attempt=lease["attempt"],
                grant=lease["grant"],
                reason=reason,
            )
        return lease


def grant_id(order: Order) -> str:
    """Identity of what authorizes an order: the approval signature, or the
    standing order plus the exact spec it covered."""
    approval = order.get("approval")
    if approval and approval.get("sig"):
        return "approval:" + hashlib.sha256(approval["sig"].encode()).hexdigest()
    return f"standing:{order['spec'].get('standing')}:{sha(order['spec'])}"


def transition(
    ledger: Ledger,
    order: Order,
    to: State,
    note: str = "",
    by: str = "st",
) -> None:
    previous = order["state"]
    if to not in TRANSITIONS[previous]:
        raise StError(f"{order['id']}: cannot go from {previous} to {to}")
    order["state"] = to
    order.setdefault("history", []).append(
        {"at": iso(now()), "from": previous, "to": to, "by": by, "note": note}
    )
    ledger.event(
        "transition", order=order["id"], frm=previous, to=to, by=by, note=note
    )
