"""Host adapters (X-1): translate a host's pre-tool hook to the guard core.

The guard core is `guard_decide(role, ToolEvent) -> reason | None` in core.py:
host-neutral, it reasons about a normalized tool call. Everything specific to
a host - how its hook delivers the event, and how allow/block is signaled -
lives in a Host here. A new host with a pre-tool hook is a Host plus a run of
the guard conformance corpus through it.

Kiro attaches a hook to each agent config, so the role arrives as `--role`.
Cursor's hooks are global, so its role comes from session bindings instead
(guard/cursor.py); this module only translates its payloads.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from ..model import AGENT_PREFIX
from ..types import JSON
from .shell import UNRESOLVED, shell_segments


@dataclass
class ToolEvent:
    """A normalized tool call: the guard core's only input besides the role."""

    tool_name: str
    tool_input: JSON = field(default_factory=dict)
    cwd: str | None = None


def team_agent_role(agent: object) -> str | None:
    """The normalized role suffix when a host name uses the team namespace.

    Agent names cross an untrusted host boundary. Namespace decisions ignore
    surrounding whitespace and case so a spelling variant cannot escape the
    team-only checks by being mistaken for an ordinary host agent.
    """
    normalized = str(agent).strip().casefold()
    if normalized.startswith(AGENT_PREFIX):
        return normalized[len(AGENT_PREFIX):]
    return None


def tool_target_paths(event: ToolEvent) -> list[object]:
    """Explicit filesystem targets carried by a normalized tool event.

    Shell command arguments are included only when they look path-like. This
    cheap pass gives the core context for commands such as ``cat /workspace/x``;
    the shell checker remains responsible for interpreting command semantics.
    """
    inp = event.tool_input
    targets: list[object] = []
    operations = inp.get("operations")
    if isinstance(operations, list):
        for operation in operations:
            if not isinstance(operation, dict):
                continue
            for field_name in ("path", "file_path", "filePath"):
                if operation.get(field_name):
                    targets.append(operation[field_name])
            images = operation.get("image_paths")
            if isinstance(images, list):
                targets.extend(images)
    for field_name in ("path", "file_path", "filePath", "working_dir"):
        if inp.get(field_name):
            targets.append(inp[field_name])
    if event.tool_name == "shell":
        targets.extend(_shell_target_paths(inp.get("command")))
    return targets


def _shell_target_paths(command: object) -> list[str]:
    if not isinstance(command, str) or not command:
        return []
    try:
        segments = shell_segments(command)
    except ValueError:
        return []
    targets: list[str] = []
    for segment in segments:
        for token in segment:
            candidates = [token]
            if token.startswith("-") and "=" in token:
                candidates.append(token.split("=", 1)[1])
            for candidate in candidates:
                if (
                    candidate
                    and not UNRESOLVED.search(candidate)
                    and not candidate.startswith(("http://", "https://"))
                    and ("/" in candidate or candidate.startswith((".", "~")))
                ):
                    targets.append(candidate)
    return targets


@dataclass
class Response:
    """What the hook process does: exit status, stdout, and stderr."""

    exit: int
    stdout: str = ""
    stderr: str = ""


def block_message(reason: str) -> str:
    return f"surgical-team guard: BLOCKED. {reason}"


def _event_object(stdin_text: str) -> JSON:
    event = json.loads(stdin_text or "{}")
    if not isinstance(event, dict):
        raise ValueError("hook event is not a JSON object")
    return event


class KiroHost:
    """Kiro CLI preToolUse hook (docs: Hooks System).

    Event is JSON on stdin: {hook_event_name, cwd, tool_name, tool_input}.
    Exit 0 allows the call; exit 2 blocks it and returns stderr to the model.
    Any other non-zero exit only warns and still allows, so the guard and the
    installed hook wrapper never exit non-zero except 2 (see H-1).
    """

    name = "kiro"
    allow_exit = 0
    block_exit = 2

    @staticmethod
    def parse(stdin_text: str) -> ToolEvent:
        # A non-object or missing fields flow into the core, which fails closed.
        event: JSON = json.loads(stdin_text or "{}")
        return ToolEvent(
            tool_name=event.get("tool_name", ""),
            tool_input=event.get("tool_input") or {},
            cwd=event.get("cwd"),
        )

    @staticmethod
    def block_message(reason: str) -> str:
        return block_message(reason)

    @classmethod
    def respond(cls, why: str | None) -> Response:
        if why:
            return Response(cls.block_exit, stderr=block_message(why))
        return Response(cls.allow_exit)


def cursor_dir() -> Path:
    # Like ST_CONFIG_DIR, the override exists for tests; the hook runs in the
    # surgeon's environment, so an agent cannot redirect it.
    return Path(os.environ.get("ST_CURSOR_DIR") or Path.home() / ".cursor")


# Cursor tool names as its preToolUse hook reports them. StrReplace arrives
# as Write, a glob as Grep with a `glob`, and a dynamic tool call under the
# inner tool's name. `Task` must map here: the shared alias table reads a
# bare "task" as Kiro's todo tool, which the core does not check.
CURSOR_TOOLS = {
    "Read": "read",
    "ReadLints": "read",
    "Write": "write",
    "Delete": "write",
    "EditNotebook": "write",
    "Shell": "shell",
    "Grep": "grep",
    "SemanticSearch": "grep",
    "Glob": "glob",
    "Task": "subagent",
    "WebSearch": "web_search",
    "WebFetch": "web_fetch",
    "TodoWrite": "todo_list",
}


class CursorHost:
    """Cursor hooks (docs: Agent > Hooks), for preToolUse and sessionStart.

    Event is JSON on stdin with conversation_id, workspace_roots, tool_name,
    and tool_input. A permission hook answers with JSON on stdout: invalid or
    missing JSON blocks, so allow is explicit. A crash or timeout is a block
    only with `failClosed: true` on the hook, which `st install` sets.
    """

    name = "cursor"

    @staticmethod
    def event_cwd(event: JSON) -> str | None:
        roots = event.get("workspace_roots") or []
        return (
            event.get("cwd")
            or (roots[0] if roots and isinstance(roots[0], str) else None)
            or os.environ.get("CURSOR_PROJECT_DIR")
        )

    @classmethod
    def parse(cls, stdin_text: str | JSON) -> ToolEvent:
        event = _event_object(stdin_text) if isinstance(stdin_text, str) else stdin_text
        raw = str(event.get("tool_name") or "")
        inp = event.get("tool_input")
        if isinstance(inp, str):  # MCP tools deliver their arguments as a JSON string
            try:
                inp = json.loads(inp)
            except ValueError:
                inp = {"raw": inp}
        if not isinstance(inp, dict):
            inp = {}
        tool, inp = cls.translate(raw, inp)
        return ToolEvent(tool_name=tool, tool_input=inp, cwd=cls.event_cwd(event))

    @staticmethod
    def translate(raw: str, inp: JSON) -> tuple[str, JSON]:
        """A Cursor tool call in the normalized shape the core and corpus use.

        Names Cursor does not define pass through unchanged, so MCP tools
        and anything new meet the core's unknown-tool refusal (E-3).
        """
        tool = CURSOR_TOOLS.get(raw)
        if tool is None:
            return raw, inp
        path = inp.get("file_path") or inp.get("path")
        if tool == "write":
            target = path or inp.get("target_notebook")
            return tool, {"file_path": target} if target else {}
        if tool == "read" and raw == "ReadLints":
            return tool, {"operations": [{"path": p} for p in inp.get("paths") or []]}
        if tool == "shell":
            out: JSON = {"command": inp.get("command", "")}
            working_dir = inp.get("cwd") or inp.get("working_directory")
            if working_dir:
                out["working_dir"] = working_dir
            return tool, out
        if tool == "grep" and raw == "SemanticSearch":
            dirs = inp.get("target_directories") or []
            if len(dirs) == 1:
                return tool, {"path": dirs[0]}
            if dirs:
                # check_read treats operation paths as content-search roots, so
                # every target independently meets blind_hit/blind_parent.
                return tool, {"operations": [{"path": directory} for directory in dirs]}
            return tool, {}  # no explicit roots: grep intentionally checks cwd
        if tool == "grep":
            if inp.get("pattern") == "" and inp.get("output_mode") == "files_with_matches":
                return "glob", {"path": path, "pattern": inp.get("glob")} if path else {}
            out = {"pattern": inp.get("pattern")}
            if path:
                out["path"] = path
            if inp.get("glob"):
                out["include"] = inp["glob"]
            return tool, out
        if tool == "glob":
            directory = inp.get("target_directory") or path
            if not directory:
                return tool, {}
            return tool, {"path": directory, "pattern": inp.get("glob_pattern")}
        if tool == "subagent":
            return tool, {"stages": [{
                "name": inp.get("description") or "task",
                "role": inp.get("subagent_type") or "",
                "prompt_template": inp.get("prompt") or "",
            }]}
        return tool, inp

    @staticmethod
    def respond(why: str | None) -> Response:
        if why:
            message = block_message(why)
            return Response(0, json.dumps(
                {"permission": "deny", "agent_message": message, "user_message": message}))
        return Response(0, json.dumps({"permission": "allow"}))


HOSTS = {host.name: host for host in (KiroHost, CursorHost)}
DEFAULT_HOST = KiroHost.name
