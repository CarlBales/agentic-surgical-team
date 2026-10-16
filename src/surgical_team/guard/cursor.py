"""The Cursor host: one global hook, with the role from session bindings.

On the supported Cursor Agent CLI, a team session is opt-in per chat: the surgeon
starts a chat with the `/st` command (installed by `st install --host cursor`).
Every other chat in the
main checkout is a plain chat and runs as ordinary Cursor. A top-level chat
rooted in an order workspace is refused regardless of its opening prompt;
workspaces belong only to the specialist dispatched there.

`st guard --host cursor` handles three events:

  sessionStart        in an interactive project with a ledger, records the chat
                      as a top-level session; nothing is injected. A background
                      session is not recorded and receives a warning.
  beforeSubmitPrompt  where the host fires it, binds a chat whose prompt is
                      `/st` as the copilot before its first tool call.
  preToolUse          resolves the conversation's role (guard/sessions.py). A
                      main-checkout top-level session becomes the copilot if
                      its transcript opens with `/st`, and plain otherwise; a
                      workspace-rooted top-level session is refused. Team roles
                      run through the guard core; plain chats pass except that
                      they cannot launch st-<role> agents.

An unbound conversation without a session record (a subagent) must claim a
pending dispatch, or it is refused in or targeting a ledger project. Without
ledger context it is also refused while a dispatch is waiting and it has no
transcript yet, since it may be that dispatch's subagent. Otherwise the call
passes through: Cursor use outside team projects is not the guard's business.
"""
from __future__ import annotations

import contextlib
import json
import os
import re
import time
from collections.abc import Callable
from pathlib import Path

from ..gitutil import existing_directory
from ..ledger import Ledger, ledger_at
from ..model import AGENT_PREFIX, StError
from ..tools import normalize_tool
from ..types import JSON
from . import sessions
from .hosts import (
    CursorHost,
    Response,
    ToolEvent,
    cursor_dir,
    team_agent_role,
    tool_target_paths,
)

WO_RE = re.compile(r"WO-\d{8}-\d{3}")
TRANSCRIPT_WAIT_S = 5.0  # well inside the hook's 15 s timeout
PLAIN = sessions.PLAIN
REFUSED = "refused"
TEAM_PROMPT_RE = re.compile(r"\s*/st(\s|$)")
TEAM_COMMAND_MARK = "--- Cursor Command: st ---"
WORKSPACE_SESSION_REFUSAL = (
    "team workspaces are only for their order's agent; a top-level Cursor Agent CLI "
    "chat cannot run there. Open the main project checkout instead, then run "
    "agent \"/st\" for a team session or start without /st for ordinary Cursor"
)

Decide = Callable[[str, ToolEvent], "str | None"]


def handle(stdin_text: str, role: str | None, decide: Decide) -> Response:
    """Answer one Cursor hook event; `decide` is the guard core's guard_decide."""
    try:
        event = json.loads(stdin_text or "{}")
    except ValueError as error:
        return CursorHost.respond(f"unparseable hook event: {error}")
    if not isinstance(event, dict):
        return CursorHost.respond("hook event is not a JSON object")
    name = event.get("hook_event_name")
    if name == "sessionStart":
        return session_start(event)
    if name == "beforeSubmitPrompt":
        return before_submit_prompt(event)
    if name == "preToolUse":
        return pre_tool_use(event, role, decide)
    return CursorHost.respond(
        f"st guard handles sessionStart, beforeSubmitPrompt, and preToolUse, not {name!r}; "
        "rerun st install --host cursor")


def workspace_layout_ledger(directory: Path) -> Ledger | None:
    """Recover a main ledger from the deterministic sibling-workspace layout.

    This path does not consult the workspace's agent-writable Git metadata.
    It is only a context detector: authority still requires the main ledger's
    signed grant and live lease, and top-level chats found here are refused.
    """
    for workspace in (directory, *directory.parents):
        if not WO_RE.fullmatch(workspace.name) or not workspace.parent.name.endswith(".st"):
            continue
        repo_name = workspace.parent.name[:-3]
        if not repo_name:
            continue
        root = workspace.parent.parent / repo_name
        ledger = Ledger(root.resolve())
        if ledger.exists() and ledger.workspace(workspace.name).resolve() == workspace.resolve():
            return ledger
    return None


def find_ledger(event: JSON, tool_event: ToolEvent | None = None) -> Ledger | None:
    """Find a team ledger from Cursor context or a normalized tool target.

    A linked worktree normally resolves through Git. If its metadata is
    unreadable or tampered, the deterministic sibling layout still recovers
    the main ledger so a top-level chat cannot fall through as plain Cursor.
    """
    roots = event.get("workspace_roots")
    candidates: list[tuple[object, str | None]] = []
    if isinstance(roots, list):
        candidates.extend((root, None) for root in roots)
    cwd = CursorHost.event_cwd(event)
    if cwd:
        candidates.append((cwd, None))
    if tool_event is not None:
        candidates.extend((target, cwd) for target in tool_target_paths(tool_event))

    seen: set[Path] = set()
    for candidate, base in candidates:
        directory = existing_directory(candidate, base)
        if directory is None or directory in seen:
            continue
        seen.add(directory)
        ledger = ledger_at(directory) or workspace_layout_ledger(directory)
        if ledger is not None:
            return ledger
    return None


def workspace_context(event: JSON, ledger: Ledger) -> Path | None:
    """An event cwd/window root inside this ledger's order-workspace base.

    Tool targets are deliberately excluded: a surgeon's ordinary chat in the
    main checkout may inspect a worktree. This rule is about where a top-level
    conversation itself is rooted.
    """
    roots = event.get("workspace_roots")
    candidates: list[object] = list(roots) if isinstance(roots, list) else []
    cwd = CursorHost.event_cwd(event)
    if cwd:
        candidates.append(cwd)
    base = ledger.workspace("x").parent.resolve()
    for candidate in candidates:
        directory = existing_directory(candidate)
        if directory is None:
            continue
        try:
            relative = directory.resolve().relative_to(base)
        except (OSError, RuntimeError, ValueError):
            continue
        if relative.parts and WO_RE.fullmatch(relative.parts[0]):
            return base / relative.parts[0]
    return None


def session_workspace(conversation: str) -> bool:
    record = sessions.session_record(conversation)
    return bool(record and record.get("workspace") is True)


def session_ledger(conversation: str, ledger: Ledger | None) -> Ledger | None:
    """Recover the main ledger from top-level provenance when event context is thin."""
    if ledger is not None:
        return ledger
    record = sessions.session_record(conversation)
    project = record.get("project") if record else None
    if not isinstance(project, str):
        return None
    candidate = Ledger(Path(project))
    return candidate if candidate.exists() else None


def session_start(event: JSON) -> Response:
    conversation = event.get("conversation_id") or event.get("session_id")
    ledger = find_ledger(event)
    if ledger is None:
        return Response(0, "{}")
    if event.get("is_background_agent") is True:
        context = (
            "Surgical-team safety warning: Cursor team sessions are supported and verified "
            "on the Cursor Agent CLI only. Do not run team sessions in the Cursor IDE; its "
            "tool calls were not observed reaching user-level hooks; never run Cursor "
            "cloud/background agents on a team project: they do not load st's user-level "
            "guard hooks, so this conversation was not bound as the copilot. Use the local "
            "Cursor Agent CLI instead; see README.md#limits-and-open-questions."
        )
        return Response(0, json.dumps({"additional_context": context}))
    if not sessions.valid_conversation(conversation):
        return Response(0, "{}")
    sessions.mark_session(
        str(conversation),
        str(ledger.root),
        workspace=workspace_context(event, ledger) is not None,
    )
    return Response(0, "{}")  # a plain chat stays invisible; /st brings the copilot


def is_team_prompt(text: str) -> bool:
    """Whether a submitted prompt starts a team session: the `/st` command."""
    return bool(TEAM_PROMPT_RE.match(text)) or TEAM_COMMAND_MARK in text


def opens_team_session(opening: str) -> bool:
    """Whether a top-level transcript opens with the `/st` command.

    Cursor records the expanded command and the literal query in the first
    user message; only the person at the keyboard can submit it.
    """
    query = re.search(r"<user_query>\s*(.*?)\s*</user_query>", opening, re.S)
    return TEAM_COMMAND_MARK in opening or bool(query and TEAM_PROMPT_RE.match(query.group(1)))


def before_submit_prompt(event: JSON) -> Response:
    """Bind a `/st` chat as the copilot early, where the host fires this hook.

    It never blocks a prompt: the guard's decisions happen at preToolUse.
    """
    with contextlib.suppress(Exception):
        conversation = event.get("conversation_id")
        prompt = event.get("prompt")
        if (sessions.valid_conversation(conversation) and isinstance(prompt, str)
                and is_team_prompt(prompt) and event.get("is_background_agent") is not True):
            conversation = str(conversation)
            ledger = find_ledger(event)
            ledger = session_ledger(conversation, ledger)
            bound = sessions.binding(conversation)
            in_workspace = session_workspace(conversation) or bool(
                ledger and workspace_context(event, ledger)
            )
            if in_workspace:
                if ledger is not None and not sessions.session_seen(conversation):
                    sessions.mark_session(conversation, str(ledger.root), workspace=True)
                sessions.bind(conversation, REFUSED)
            elif ledger is not None and (bound is None or bound.get("role") == PLAIN):
                sessions.mark_session(conversation, str(ledger.root))
                sessions.bind(conversation, "copilot")
    return Response(0, json.dumps({"continue": True}))


def cursor_project_slug(root: str) -> str:
    """Map a workspace root to Cursor's directory name under projects/."""
    return re.sub(r"[^A-Za-z0-9]+", "-", root).strip("-")


def workspace_project_slugs(event: JSON) -> list[str]:
    """Project slugs derived only from well-formed event workspace roots."""
    roots = event.get("workspace_roots")
    if not isinstance(roots, list):
        return []
    slugs: list[str] = []
    for root in roots:
        if not isinstance(root, str):
            continue
        slug = cursor_project_slug(root)
        if slug and slug not in slugs:
            slugs.append(slug)
    return slugs


def transcript_opening(event: JSON, conversation: str) -> str | None:
    """The first user message of a conversation: for a subagent, its Task prompt.

    None when no transcript is found, which differs from an empty opening: a
    conversation with a transcript that matches no dispatch is not a team
    subagent, while one with no transcript yet may be.
    """
    projects = cursor_dir() / "projects"
    candidates: list[Path] = []
    if event.get("transcript_path"):
        candidates.append(Path(str(event["transcript_path"])))
    for slug in workspace_project_slugs(event):
        transcripts = projects / slug / "agent-transcripts"
        candidates.append(transcripts / conversation / f"{conversation}.jsonl")
    for path in candidates:
        if path.is_file():
            break
    else:
        found = [*projects.glob(f"*/agent-transcripts/{conversation}/{conversation}.jsonl"),
                 *projects.glob(f"*/agent-transcripts/*/subagents/{conversation}.jsonl")]
        if not found:
            return None
        path = found[0]
    try:
        with path.open() as fh:
            first = json.loads(fh.readline() or "{}")
    except OSError:
        return None
    except ValueError:
        return ""
    content = (first.get("message") or {}).get("content") if isinstance(first, dict) else None
    if isinstance(content, str):
        return content
    return "\n".join(
        str(part.get("text", "")) for part in content or [] if isinstance(part, dict)
    )


def transcript_wait_s() -> float:
    # Under load a subagent's first tool call can reach the hook before Cursor
    # has written its transcript (seen live: a refused first call, then a
    # claim a moment later). Tests shorten the wait; like ST_NOW, only when
    # ST_CONFIG_DIR marks a test sandbox. A shorter wait only refuses sooner.
    override = os.environ.get("ST_CURSOR_TRANSCRIPT_WAIT_S")
    if override and os.environ.get("ST_CONFIG_DIR"):
        with contextlib.suppress(ValueError):
            return max(0.0, float(override))
    return TRANSCRIPT_WAIT_S


def await_transcript_opening(event: JSON, conversation: str) -> str | None:
    """transcript_opening, waiting briefly while the transcript is missing or empty."""
    deadline = time.monotonic() + transcript_wait_s()
    while True:
        opening = transcript_opening(event, conversation)
        if opening or time.monotonic() >= deadline:
            return opening
        time.sleep(0.1)


def scratch_write(event: JSON, tool_event: ToolEvent) -> bool:
    """Recognize Cursor's own spill of large tool output.

    The exemption is deliberately narrower than the normalized write tool:
    recorded spills use raw `Write`, not `Delete`, and must target agent-tools/
    under a project slug derived from this event's own workspace roots. The
    caller resolves the conversation's role before applying the exemption.
    """
    if event.get("tool_name") != "Write" or not tool_event.tool_input.get("file_path"):
        return False
    try:
        relative = Path(str(tool_event.tool_input["file_path"])).resolve().relative_to(
            (cursor_dir() / "projects").resolve())
    except (OSError, RuntimeError, ValueError):
        return False
    return (
        len(relative.parts) == 3
        and relative.parts[0] in workspace_project_slugs(event)
        and relative.parts[1] == "agent-tools"
    )


def _missing_ledger_context_refusal() -> str | None:
    if not sessions.has_pending_dispatch():
        return None
    return (
        "this unbound conversation has no ledger context and no transcript yet, while a "
        "pending team dispatch exists, so it may be that dispatch's specialist. Cursor "
        "must provide workspace_roots, cwd, or a tool target inside the team project so "
        "the specialist can bind; retry from its Cursor Agent CLI project directory"
    )


def resolve_role(event: JSON, ledger: Ledger | None) -> tuple[str | None, str | None]:
    """(role, None), or (None, refusal), or (None, None) to pass through."""
    conversation = event.get("conversation_id")
    if not sessions.valid_conversation(conversation):
        if ledger is None:
            return None, _missing_ledger_context_refusal()
        return None, "the hook event carries no valid conversation_id"
    conversation = str(conversation)
    top_level = sessions.session_seen(conversation)
    context_ledger = session_ledger(conversation, ledger) if top_level else ledger
    if top_level and (
        session_workspace(conversation)
        or bool(context_ledger and workspace_context(event, context_ledger))
    ):
        sessions.bind(conversation, REFUSED)
        return None, WORKSPACE_SESSION_REFUSAL
    bound = sessions.binding(conversation)
    if bound:
        if bound.get("role") == REFUSED:
            return None, WORKSPACE_SESSION_REFUSAL
        return str(bound.get("role")), None
    # A session record is positive top-level provenance. It must win over a
    # transcript match so pruning can never turn a copilot into a specialist.
    # The chat's own first message decides copilot or plain, once.
    if sessions.session_seen(conversation):
        opening = await_transcript_opening(event, conversation)
        if not opening:
            return None, (
                f"cannot tell whether chat {conversation} is a team session: its transcript "
                "is not readable yet. Retry; if this persists, start a new Cursor Agent CLI "
                "chat with agent \"/st\""
            )
        role = "copilot" if opens_team_session(opening) else PLAIN
        return str(sessions.bind(conversation, role)["role"]), None
    # Without a pending dispatch nothing can be claimed, so ordinary chats
    # elsewhere skip the transcript lookup.
    pending = sessions.has_pending_dispatch()
    opening = await_transcript_opening(event, conversation) if pending else None
    claimed = sessions.claim(conversation, opening) if opening else None
    if claimed:
        return str(claimed["role"]), None
    if ledger is None:
        # A transcript that matches no dispatch is an ordinary chat elsewhere;
        # only a conversation that cannot be identified yet is held back.
        if pending and opening is None:
            return None, _missing_ledger_context_refusal()
        return None, None
    return None, (
        f"conversation {conversation} is not bound to a team role. In a project with a "
        "ledger, an Agent CLI chat started with /st is the copilot, and specialists bind "
        f"from the copilot's Task call; run agent \"/st\", or dispatch {AGENT_PREFIX}<role> "
        "from it with the st dispatch briefing verbatim"
    )


def plain_tool_use(tool_event: ToolEvent, ledger: Ledger | None, parent: str) -> Response:
    """A plain chat (or its subagent) is ordinary Cursor: the guard stays out,
    except that team agents start only from a team session."""
    if normalize_tool(tool_event.tool_name) != "subagent":
        return CursorHost.respond(None)
    stages = tool_event.tool_input.get("stages") or []
    if any(team_agent_role(stage.get("role", "")) is not None for stage in stages):
        return CursorHost.respond(
            f"{AGENT_PREFIX}<role> agents run only from a team session; start a new Cursor "
            "Agent CLI chat with agent \"/st\" and let the copilot dispatch the order")
    for stage in stages:  # so its subagents bind as plain too, not as unknown
        sessions.add_pending(str(stage.get("prompt_template", "")), PLAIN, None, parent)
    return CursorHost.respond(None)


def pre_tool_use(event: JSON, role: str | None, decide: Decide) -> Response:
    tool_event = CursorHost.parse(event)
    ledger = find_ledger(event, tool_event)
    if not role:
        role, refusal = resolve_role(event, ledger)
        if refusal:
            return CursorHost.respond(refusal)
        if role is None:
            return CursorHost.respond(None)
    if role == PLAIN:
        return plain_tool_use(tool_event, ledger, str(event.get("conversation_id", "")))
    if scratch_write(event, tool_event):
        return CursorHost.respond(None)
    why = decide(role, tool_event)
    if why is None and role == "copilot" and normalize_tool(tool_event.tool_name) == "subagent":
        record_dispatches(tool_event, ledger, str(event.get("conversation_id", "")))
    return CursorHost.respond(why)


def record_dispatches(event: ToolEvent, ledger: Ledger | None, parent: str) -> None:
    for stage in event.tool_input.get("stages") or []:
        agent = str(stage.get("role", ""))
        role = team_agent_role(agent)
        if role is None:
            raise StError(f"allowed subagent name {agent!r} is outside the team namespace")
        prompt = str(stage.get("prompt_template", ""))
        wo = None
        for candidate in WO_RE.findall(prompt):
            with contextlib.suppress(StError, OSError, KeyError, ValueError):
                if ledger and ledger.order(candidate)["spec"]["role"] == role:
                    wo = candidate
                    break
        sessions.add_pending(prompt, role, wo, parent)
