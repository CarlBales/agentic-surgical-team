"""Constants, the error type, time, and canonical hashing."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re

from .types import Level, ReportStatus, State

VERSION = "0.6.0"

NAMESPACE = "surgical-team"
LEDGER_DIRNAME = ".surgical-team"
LEVELS: dict[Level, int] = {"L0": 0, "L1": 1, "L2": 2}
ROLE_NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
NON_ROLE_FAMILIES = {"protocol"}
WO_RE = re.compile(r"^WO-\d{8}-\d{3}$")
DEC_RE = re.compile(r"^DEC-\d{3,}$")
REPORT_STATUSES: set[ReportStatus] = {"DONE", "PARTIAL", "BLOCKED", "DECLINED"}
SURGEON_CMDS = {
    "setup",
    "init",
    "approve",
    "accept",
    "reject",
    "defer",
    "cancel",
    "decide",
    "grant",
    "revoke",
    "install",
    "uninstall",
    "migrate",
    "prune",
}
SPECIALIST_ST_CMDS = {"brief", "show", "list", "status", "report", "verify", "check",
                      "doctor"}
AGENT_PREFIX = "st-"  # agent names on every host: st-copilot, st-tester, ...
TERMINAL: set[State] = {"accepted", "rejected", "cancelled"}
TRANSITIONS: dict[State, set[State]] = {
    "drafted": {"approved", "dispatched", "drafted", "cancelled"},
    "approved": {"dispatched", "drafted", "cancelled"},
    "dispatched": {"reported", "approved", "drafted", "cancelled"},
    "reported": {"accepted", "rejected", "deferred", "drafted", "cancelled"},
    "deferred": {"accepted", "rejected", "drafted", "cancelled"},
    "accepted": set(),
    "rejected": set(),
    "cancelled": set(),
}
DEFAULT_CHECK_TIMEOUT = 600
STALE_FACTOR = 2  # dispatched with no report after budget x this is stale


class StError(Exception):
    pass


def now() -> dt.datetime:
    # ST_NOW moves the clock for tests (expiry, staleness). It is honored only
    # when ST_CONFIG_DIR is also set, i.e. in a test sandbox: a real install
    # uses the default config directory, so a planted ST_NOW in the surgeon's
    # environment cannot shift the clock the guard judges approvals against
    # (M-8).
    override = os.environ.get("ST_NOW")
    if override and os.environ.get("ST_CONFIG_DIR"):
        return parse_iso(override)
    return dt.datetime.now(dt.timezone.utc)


def iso(t: dt.datetime) -> str:
    return t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(s: str) -> dt.datetime:
    t = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)


def canon(obj: object) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def sha(obj: object) -> str:
    return hashlib.sha256(canon(obj)).hexdigest()
