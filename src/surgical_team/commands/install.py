"""st install: guarded role agents for a host (Kiro configs or Cursor subagents)."""
from __future__ import annotations

import argparse
import json
import re
import shlex
from pathlib import Path

from ..agents import copilot_command, inlined_skills, role_description, role_prompt
from ..guard.hosts import cursor_dir
from ..model import AGENT_PREFIX, StError
from ..roles import TEAM_ROOT, team_roles
from ..types import JSON

ROLE_TOOLS: dict[str, list[str]] = {
    "copilot": [
        "read",
        "glob",
        "grep",
        "code",
        "shell",
        "write",
        "subagent",
        "todo_list",
        "web_search",
        "web_fetch",
    ],
    "_specialist": [
        "read",
        "glob",
        "grep",
        "code",
        "shell",
        "write",
        "web_search",
        "web_fetch",
        "use_aws",
    ],
}
CURSOR_HOOK_MARK = "guard --host cursor"
CURSOR_HOOK_EVENTS = ("sessionStart", "beforeSubmitPrompt", "preToolUse")
CURSOR_COMMAND = "st"  # typed as /st to start a team session


def guard_hook_command(st: str, role: str) -> str:
    """The preToolUse hook command for a role, failing closed.

    Kiro blocks a tool call only when the hook exits 2; any other non-zero
    exit shows a warning and *allows* the call. So a guard that cannot run
    (interpreter missing, import error, crash) must not exit 1. The wrapper
    maps every non-zero, non-2 status to 2, including failures before
    Python starts, and says why on stderr.
    """
    guard = f"{shlex.quote(st)} guard --role {shlex.quote(role)}"
    return (f"{guard}; s=$?; [ $s -eq 0 ] || [ $s -eq 2 ] || "
            f"{{ echo \"surgical-team guard: BLOCKED. guard exited $s, failing closed\" >&2; "
            f"exit 2; }}; exit $s")


def agent_config(role: str, team_root: Path) -> JSON:
    st = str(team_root / "bin" / "st")
    skills = team_root / "skills"
    specialist = role != "copilot"
    config: JSON = {
        "name": f"{AGENT_PREFIX}{role}",
        "description": role_description(role, team_root),
        "prompt": role_prompt(role, team_root),
        "tools": ROLE_TOOLS["_specialist" if specialist else "copilot"],
        # Read tools are auto-approved everywhere. Specialists also run write
        # and shell without prompts: they are subagents with no one to answer
        # a prompt, and the guard, not a prompt, is the control.
        "allowedTools": ["read", "glob", "grep", "code"]
        + (["write", "shell", "use_aws"] if specialist else []),
        "toolsSettings": {
            "shell": {
                "allowedCommands": [
                    rf"{re.escape(st)} (status|list|show|brief|verify)\b.*",
                    r"st (status|list|show|brief|verify)\b.*",
                ],
                "autoAllowReadonly": True,
            }
        },
        "resources": [
            f"file://{skills / 'surgical-team-protocol' / 'SKILL.md'}",
            f"file://{skills / role / 'SKILL.md'}",
            f"skill://{skills / 'surgical-team-protocol' / 'references'}/*.md",
        ],
        "hooks": {
            "preToolUse": [
                {
                    "matcher": "*",
                    "command": guard_hook_command(st, role),
                    "timeout_ms": 15000,
                }
            ]
        },
    }
    if not specialist:
        config["toolsSettings"]["crew"] = {"availableAgents": [f"{AGENT_PREFIX}*"]}
        config["hooks"]["agentSpawn"] = [
            {"command": f"{shlex.quote(st)} status 2>&1 || true"}
        ]
    return config


def cursor_agent_md(role: str, team_root: Path) -> str:
    """A Cursor subagent file for a specialist.

    Cursor subagents cannot carry a hook or load skills by reference, so the
    skills are inlined and the guard is the global hook (cursor_hooks). The
    copilot is not a subagent: it is an Agent CLI chat the surgeon starts with
    `/st` (cursor_command_path).
    """
    description = (
        f"{role_description(role, team_root)}. Surgical team only: launched by the "
        "copilot with an `st dispatch` briefing, never for general work."
    )
    return (
        "---\n"
        f"name: {AGENT_PREFIX}{role}\n"
        f"description: {json.dumps(description)}\n"
        "model: inherit\n"
        "---\n\n"
        f"{role_prompt(role, team_root, host='cursor')}\n\n"
        f"{inlined_skills(role, team_root)}\n"
    )


def cursor_hooks(team_root: Path) -> dict[str, list[JSON]]:
    """The hook entries `st install --host cursor` owns in hooks.json.

    `failClosed` makes a crash or timeout a block; a permission hook already
    blocks on missing or invalid JSON.
    """
    command = f"{shlex.quote(str(team_root / 'bin' / 'st'))} {CURSOR_HOOK_MARK}"
    return {
        "sessionStart": [{"command": command, "timeout": 15}],
        # Only an early copilot binding; it always answers continue.
        "beforeSubmitPrompt": [{"command": command, "timeout": 15}],
        "preToolUse": [{"command": command, "matcher": "*", "failClosed": True, "timeout": 15}],
    }


def is_team_hook(entry: object) -> bool:
    return isinstance(entry, dict) and CURSOR_HOOK_MARK in str(entry.get("command", ""))


def merge_cursor_hooks(existing: JSON, team_root: Path) -> JSON:
    """`existing` with the team's entries replaced and every other hook kept.

    Event lists are otherwise opaque: non-team entries, including non-object
    entries, are preserved exactly. Refusing malformed event shapes avoids a
    "repair" that silently erases user configuration.
    """
    merged: JSON = {**existing, "version": existing.get("version", 1)}
    hooks = merged.get("hooks") or {}
    if not isinstance(hooks, dict):
        raise StError("hooks.json: `hooks` is not an object; fix it by hand first")
    kept_hooks: JSON = {}
    for event, entries in hooks.items():
        if not isinstance(entries, list):
            raise StError(
                f"hooks.json: hook event `{event}` is not a list; fix it by hand first"
            )
        kept_hooks[event] = [entry for entry in entries if not is_team_hook(entry)]
    hooks = kept_hooks
    for event, entries in cursor_hooks(team_root).items():
        hooks[event] = [*hooks.get(event, []), *entries]
    merged["hooks"] = {event: entries for event, entries in hooks.items() if entries}
    return merged


def cursor_command_path(args: argparse.Namespace | None = None) -> Path:
    custom = getattr(args, "commands", None) if args is not None else None
    directory = Path(custom).expanduser() if custom else cursor_dir() / "commands"
    return directory / f"{CURSOR_COMMAND}.md"


def install_kiro(args: argparse.Namespace) -> None:
    destination = (
        Path(args.dir).expanduser() if args.dir else Path.home() / ".kiro" / "agents"
    )
    destination.mkdir(parents=True, exist_ok=True)
    for role in team_roles(TEAM_ROOT):
        config = agent_config(role, TEAM_ROOT)
        path = destination / f"{config['name']}.json"
        path.write_text(json.dumps(config, indent=2) + "\n")
        print(f"wrote {path}")
    print(f"start a session with: kiro-cli chat --agent {AGENT_PREFIX}copilot")


def install_cursor(args: argparse.Namespace) -> None:
    destination = Path(args.dir).expanduser() if args.dir else cursor_dir() / "agents"
    hooks_path = Path(args.hooks).expanduser() if args.hooks else cursor_dir() / "hooks.json"
    existing: JSON = {}
    if hooks_path.exists():
        try:
            existing = json.loads(hooks_path.read_text())
        except ValueError as error:
            raise StError(
                f"{hooks_path} is not valid JSON ({error}); fix it by hand first") from error
        if not isinstance(existing, dict):
            raise StError(f"{hooks_path} is not a JSON object; fix it by hand first")
    merged = merge_cursor_hooks(existing, TEAM_ROOT)
    destination.mkdir(parents=True, exist_ok=True)
    for role in team_roles(TEAM_ROOT):
        if role == "copilot":
            continue
        path = destination / f"{AGENT_PREFIX}{role}.md"
        path.write_text(cursor_agent_md(role, TEAM_ROOT))
        print(f"wrote {path}")
    command = cursor_command_path(args)
    command.parent.mkdir(parents=True, exist_ok=True)
    command.write_text(copilot_command(TEAM_ROOT))
    print(f"wrote {command}")
    hooks_path.parent.mkdir(parents=True, exist_ok=True)
    hooks_path.write_text(json.dumps(merged, indent=2) + "\n")
    print(f"wrote {hooks_path} (st guard on {', '.join(CURSOR_HOOK_EVENTS)}; other hooks kept)")
    print("start a team session (supported and verified on the Cursor Agent CLI only): "
          f"in a project with a ledger, run agent \"/{CURSOR_COMMAND}\". Do not use "
          "the Cursor IDE: its tool calls were not observed reaching user-level hooks; see "
          f"{TEAM_ROOT / 'README.md'}#limits-and-open-questions. Every other Agent CLI chat "
          "stays ordinary Cursor")


def cmd_install(args: argparse.Namespace) -> None:
    host = getattr(args, "host", "kiro")
    if host == "cursor":
        install_cursor(args)
    elif host == "kiro":
        if getattr(args, "hooks", None) or getattr(args, "commands", None):
            raise StError("--hooks and --commands are for --host cursor")
        install_kiro(args)
    else:
        raise StError(f"unknown host {host!r}; known: cursor, kiro")
