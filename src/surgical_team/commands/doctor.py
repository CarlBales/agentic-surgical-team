"""st doctor: check the environment the team depends on (X-2)."""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from ..guard.hosts import DEFAULT_HOST, HOSTS, cursor_dir
from ..ledger import FORMAT, Ledger
from ..model import AGENT_PREFIX, VERSION, StError
from ..roles import TEAM_ROOT, team_roles
from ..signing import config_dir, load_config
from ..agents import copilot_command
from .footprint import footprint
from .install import cursor_agent_md, cursor_command_path, cursor_hooks

OK, WARN, BAD = "ok", "warn", "FAIL"


class Report:
    def __init__(self) -> None:
        self.rows: list[tuple[str, str, str]] = []

    def add(self, status: str, name: str, detail: str) -> None:
        self.rows.append((status, name, detail))

    def worst(self) -> str:
        if any(s == BAD for s, _, _ in self.rows):
            return BAD
        if any(s == WARN for s, _, _ in self.rows):
            return WARN
        return OK


def _run(args: list[str]) -> tuple[int, str]:
    try:
        result = subprocess.run(args, check=False, capture_output=True, text=True)
    except FileNotFoundError:
        return 127, ""
    return result.returncode, (result.stdout + result.stderr).strip()


def _tool_version(report: Report, name: str, args: list[str], pattern: str,
                  minimum: tuple[int, ...] | None = None) -> None:
    if shutil.which(args[0]) is None:
        report.add(BAD, name, f"{args[0]} not found on PATH")
        return
    code, out = _run(args)
    match = re.search(pattern, out)
    if code != 0 or not match:
        report.add(WARN, name, f"could not read version from {out[:60]!r}")
        return
    version = tuple(int(part) for part in match.group(1).split("."))
    if minimum and version < minimum:
        report.add(BAD, name, f"{match.group(1)} < {'.'.join(map(str, minimum))} required")
    else:
        report.add(OK, name, match.group(1))


def _check_python(report: Report) -> None:
    v = sys.version_info
    status = OK if v >= (3, 9) else BAD
    report.add(status, "python", f"{v.major}.{v.minor}.{v.micro} (floor 3.9)")


def _check_signing(report: Report) -> None:
    config = load_config()
    key, identity = config.get("key"), config.get("identity")
    if not key or not identity:
        report.add(BAD, "signing key", "not configured; run: st setup --key PATH --identity NAME")
        return
    key_path = Path(key)
    public = key_path if key_path.suffix == ".pub" else key_path.with_name(key_path.name + ".pub")
    if not public.exists():
        report.add(BAD, "signing key", f"public key missing at {public}")
        return
    hardware = public.read_text().startswith(("sk-", "sk-ssh"))
    if key_path != public and not hardware:
        code, _ = _run(["ssh-keygen", "-y", "-P", "", "-f", str(key_path)])
        if code == 0:
            report.add(BAD, "signing policy",
                       f"{key_path} signs with no passphrase; workspace code could sign "
                       "approvals (st setup refuses this without --allow-unencrypted)")
            return
    report.add(OK, "signing key", f"{identity} ({'hardware' if hardware else 'protected'})")


def _check_trust_root(report: Report) -> None:
    signers = config_dir() / "allowed_signers"
    if not signers.exists():
        report.add(BAD, "allowed_signers", f"missing at {signers}")
        return
    try:
        mode = signers.parent.stat().st_mode & 0o077
    except OSError as error:
        report.add(WARN, "allowed_signers", f"cannot stat: {error}")
        return
    n = len([line for line in signers.read_text().splitlines() if line.strip()])
    note = " (config dir is group/other-accessible)" if mode else ""
    report.add(WARN if mode else OK, "allowed_signers", f"{n} signer(s) at {signers}{note}")


def _installed(agents_dir: Path, suffix: str) -> set[str]:
    if not agents_dir.is_dir():
        return set()
    return {p.stem[len(AGENT_PREFIX):] for p in agents_dir.glob(f"{AGENT_PREFIX}*{suffix}")}


def _agents_row(report: Report, host: str, installed: set[str], roles: set[str],
                outdated: list[str]) -> None:
    install = "st install" + ("" if host == "kiro" else f" --host {host}")
    missing = sorted(roles - installed)
    removed = sorted(installed - roles)
    detail = f"{len(installed & roles)}/{len(roles)} role agents present"
    if missing:
        detail += f"; missing {', '.join(missing)} (run: {install})"
    if removed:
        detail += f"; stale {', '.join(AGENT_PREFIX + s for s in removed)} (skills removed)"
    if outdated:
        detail += f"; out of date {', '.join(AGENT_PREFIX + s for s in outdated)} (run: {install})"
    report.add(WARN if (missing or removed or outdated) else OK,
               f"installed agents ({host})", detail)


def _check_installed_agents(report: Report) -> None:
    roles = set(team_roles())
    kiro_dir = Path.home() / ".kiro" / "agents"
    cursor_agents = cursor_dir() / "agents"
    kiro = _installed(kiro_dir, ".json")
    cursor = _installed(cursor_agents, ".md")
    hooks_path = cursor_dir() / "hooks.json"
    if not (kiro or cursor):
        report.add(WARN, "installed agents",
                   f"none at {kiro_dir} or {cursor_agents}; run: st install [--host cursor]")
        return
    if kiro:
        _agents_row(report, "kiro", kiro, roles, [])
    if cursor:
        # The copilot is Cursor's top-level chat, not a subagent file.
        outdated = sorted(
            role for role in cursor & roles
            if (cursor_agents / f"{AGENT_PREFIX}{role}.md").read_text()
            != cursor_agent_md(role, TEAM_ROOT)
        )
        _agents_row(report, "cursor", cursor | {"copilot"}, roles, outdated)
        _check_cursor_hooks(report, hooks_path)
        command = cursor_command_path()
        if not command.is_file():
            report.add(BAD, "cursor /st command",
                       f"missing at {command}; team sessions cannot start "
                       "(run: st install --host cursor)")
        elif command.read_text() != copilot_command(TEAM_ROOT):
            report.add(WARN, "cursor /st command",
                       f"out of date at {command} (run: st install --host cursor)")
        else:
            report.add(OK, "cursor /st command",
                       f'{command}; run agent "/st" in the Cursor Agent CLI only')
        # A standing fact, not a fault: a WARN here would make every healthy
        # Cursor install read as degraded and hide real warnings.
        report.add(OK, "cursor cloud agents",
                   "Cursor team sessions are supported and verified on the Cursor Agent "
                   "CLI only; do not run team sessions in the Cursor IDE (its tool calls "
                   "were not observed reaching user-level hooks); cloud/background agents "
                   "skip those hooks, so never use them on team projects; see "
                   f"{TEAM_ROOT / 'README.md'}#limits-and-open-questions")
        cli = shutil.which("cursor-agent") or shutil.which("agent")
        if cli:
            _tool_version(report, "cursor-agent", [cli, "--version"], r"(\d+\.\d+\.\d+)")
        else:
            report.add(WARN, "cursor-agent",
                       "not on PATH; install the Agent CLI for supported Cursor team sessions")


def _check_cursor_hooks(report: Report, path: Path) -> None:
    try:
        hooks = json.loads(path.read_text()).get("hooks") or {}
    except (OSError, ValueError, AttributeError):
        report.add(BAD, "cursor hooks", f"no readable {path}; the guard is not installed "
                                        "(run: st install --host cursor)")
        return
    want = cursor_hooks(TEAM_ROOT)
    missing = [event for event, entries in want.items()
               if not any(entry in (hooks.get(event) or []) for entry in entries)]
    if missing:
        report.add(BAD, "cursor hooks", f"{path} lacks this st's guard on {', '.join(missing)} "
                                        "(run: st install --host cursor)")
    else:
        report.add(OK, "cursor hooks", f"guard on {', '.join(want)} in {path}")


def _check_ledger(report: Report) -> None:
    try:
        ledger = Ledger.at()
    except StError:
        report.add(OK, "ledger", "not in a project with a ledger (run st init in one)")
        return
    if not ledger.exists():
        report.add(OK, "ledger", f"no ledger at {ledger.dir} (run: st init)")
        return
    fmt = ledger.format()
    if fmt == FORMAT:
        report.add(OK, "ledger", f"format {fmt} at {ledger.dir}")
        _check_footprint(report, ledger)
    elif isinstance(fmt, int) and fmt < FORMAT:
        report.add(WARN, "ledger", f"format {fmt} < {FORMAT}; run: st migrate")
    else:
        report.add(BAD, "ledger", f"format {fmt!r} is not readable by st {VERSION}")


def _check_footprint(report: Report, ledger: Ledger) -> None:
    """What the team leaves around the project besides the ledger."""
    found = footprint(ledger)
    detail = (f"{len(found['workspaces'])} workspace(s) in {found['base']}, "
              f"{found['branches']} st/* branch(es)")
    if found["closed"]:
        detail += (f"; {len(found['closed'])} closed order(s) still have a workspace "
                   "(st prune --dry-run shows what can go)")
    report.add(OK, "footprint", detail)


def _check_guard_latency(report: Report) -> None:
    st = Path(sys.argv[0]).resolve()
    event = json.dumps({"tool_name": "read", "cwd": str(Path.cwd()),
                        "tool_input": {"operations": [{"mode": "Line", "path": "README.md"}]}})
    times = []
    for _ in range(5):
        start = time.perf_counter()
        subprocess.run([sys.executable, str(st), "guard", "--role", "copilot"],
                       input=event, check=False, capture_output=True, text=True)
        times.append((time.perf_counter() - start) * 1000)
    times.sort()
    report.add(OK, "guard latency", f"~{times[len(times) // 2]:.0f} ms per call (read, no orders)")


def cmd_doctor(args: argparse.Namespace) -> int:
    report = Report()
    _check_python(report)
    _tool_version(report, "git", ["git", "--version"], r"(\d+\.\d+(?:\.\d+)?)", (2, 5))
    _tool_version(report, "ssh-keygen", ["ssh", "-V"], r"OpenSSH[_ ](\d+\.\d+)", (8, 1))
    _check_signing(report)
    _check_trust_root(report)
    report.add(OK, "host", f"guard hosts: {', '.join(sorted(HOSTS))} (default {DEFAULT_HOST})")
    _check_installed_agents(report)
    _check_ledger(report)
    if not args.quick:
        _check_guard_latency(report)
    width = max(len(name) for _, name, _ in report.rows)
    marks = {OK: "ok  ", WARN: "warn", BAD: "FAIL"}
    for status, name, detail in report.rows:
        print(f"  [{marks[status]}] {name.ljust(width)}  {detail}")
    worst = report.worst()
    print(f"\nst {VERSION}: {'all good' if worst == OK else worst}")
    return 1 if worst == BAD else 0
