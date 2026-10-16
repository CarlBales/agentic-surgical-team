"""st guard: the preToolUse hook that enforces authority on every tool call."""
from __future__ import annotations

import argparse
import contextlib
import fnmatch
import os
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from ..authority import live_orders
from ..gitutil import existing_directory, is_within
from ..guard.hosts import (
    DEFAULT_HOST,
    HOSTS,
    CursorHost,
    KiroHost,
    Response,
    ToolEvent,
    block_message,
    cursor_dir,
    team_agent_role,
    tool_target_paths,
)
from ..guard.cursor import handle as cursor_handle
from ..guard.shellcheck import GuardShell
from ..ledger import Leases, Ledger, clear_ledger_cache, ledger_at
from ..model import AGENT_PREFIX, LEDGER_DIRNAME, StError, sha
from ..roles import TEAM_ROOT, is_role
from ..signing import config_dir, load_config
from ..tools import (
    AWS_TOOL,
    CODE_WRITE_OPS,
    KNOWN_TOOLS,
    aws_op,
    aws_op_refusal,
    normalize_tool,
)
from ..types import JSON, Order

if TYPE_CHECKING:
    ActiveOrder = tuple[Order, int, bool, Path | None]

WO_ID_RE = re.compile(r"WO-\d{8}-\d{3}")
BRIEFING_HEADER_RE = re.compile(r"Work order (WO-\d{8}-\d{3})\b", re.I)


class Guard(GuardShell):
    def __init__(self, role: str, event: ToolEvent) -> None:
        self.role = role
        self.cwd = Path(event.cwd or os.getcwd()).resolve()
        self.home = Path.home().resolve()
        self.context_refusal: str | None = None

        cwd_ledger = self._ledger_at(self.cwd)
        target_ledgers: dict[Path, Ledger] = {}
        seen_directories: set[Path] = set()
        for target in tool_target_paths(event):
            directory = existing_directory(target, self.cwd)
            if directory is None or directory in seen_directories:
                continue
            seen_directories.add(directory)
            # Normal calls within the cwd checkout need no second git lookup.
            # Explicit paths outside it are checked so one call cannot cross
            # team ledgers, while fallback discovery still happens when cwd is
            # a parent window or unrelated directory.
            if cwd_ledger and (
                self._same_checkout_path(directory, cwd_ledger.root)
                or self._same_checkout_path(directory, self.cwd)
            ):
                continue
            ledger = self._ledger_at(directory)
            if ledger is not None:
                target_ledgers[ledger.root] = ledger

        self.L: Ledger | None = cwd_ledger
        if cwd_ledger is not None:
            different = sorted(
                root for root in target_ledgers if root != cwd_ledger.root
            )
            if different:
                roots = ", ".join(str(root) for root in different)
                self.context_refusal = (
                    f"a tool target resolves to team ledger {roots}, which differs from "
                    f"the event cwd ledger {cwd_ledger.root}; one tool call cannot cross "
                    "team ledgers"
                )
        elif len(target_ledgers) > 1:
            roots = ", ".join(str(root) for root in sorted(target_ledgers))
            self.context_refusal = (
                f"tool targets resolve to multiple team ledgers ({roots}); split the "
                "operation so each tool call has exactly one ledger context"
            )
        elif target_ledgers:
            # Finding a ledger selects context only. Authority remains derived
            # exclusively from this ledger's signed grants and local leases.
            self.L = next(iter(target_ledgers.values()))

        self._active: list[ActiveOrder] | None = None
        self._blind: list[tuple[Order, Path | None]] | None = None
        config = load_config()
        key = config.get("key")
        self.secrets = [self.home / ".ssh"]
        if key:
            key_path = Path(key)
            self.secrets.append(
                key_path.with_suffix("") if key_path.suffix == ".pub" else key_path
            )
        self.protected = [
            path
            for path in [
                self.L.dir if self.L else None,
                config_dir(),
                self.home / ".kiro" / "agents",
                (self.L.root / ".kiro") if self.L else None,
                # Cursor's agents, hooks, and the transcripts that bind roles.
                cursor_dir(),
                (self.L.root / ".cursor") if self.L else None,
                TEAM_ROOT,
                self.home / ".ssh",
            ]
            if path is not None
        ]

    @staticmethod
    def _same_checkout_path(directory: Path, root: Path) -> bool:
        if not is_within(directory, root):
            return False
        current = directory
        while current != root:
            if (current / ".git").exists():
                return False
            current = current.parent
        return True

    @staticmethod
    def _ledger_at(directory: Path) -> Ledger | None:
        return ledger_at(directory)

    @property
    def active(self) -> list[ActiveOrder]:
        """This role's live orders: (order, level, push, workspace).

        Computed on first use (P-1), so a decision that needs no authority,
        such as a read outside any blind order or a write to a protected
        path, verifies no signatures.

        Authority comes from the local lease store and signatures, never
        from the ledger's state field. The workspace is derived from the
        order ID, never read from the (unsigned) dispatch record. Only this
        role's leases are verified; the copilot's subagent check, which
        needs every role's, verifies them itself.
        """
        if self._active is None:
            active: list[ActiveOrder] = []
            if self.L and self.L.exists():
                for order, _lease, level, push in live_orders(self.L, self.role):
                    if order["spec"]["role"] != self.role:
                        continue
                    workspace = self.L.workspace(order["id"]) if level >= 1 else None
                    active.append((order, level, push, workspace))
            self._active = active
        return self._active

    # helpers
    def resolve(self, path: object, base: Path) -> Path:
        expanded = Path(os.path.expanduser(str(path)))
        return (expanded if expanded.is_absolute() else base / expanded).resolve()

    def lexical_path(self, path: object, base: Path) -> Path:
        """Normalize dot segments without following links, for path-name policy.

        Canonical resolution still decides confinement. This second form keeps
        a literal ``.git`` component visible even when a build previously
        replaced that entry with a symlink inside the workspace.
        """
        expanded = Path(os.path.expanduser(str(path)))
        candidate = expanded if expanded.is_absolute() else base / expanded
        return Path(os.path.abspath(candidate))

    def workspace_git_metadata_hit(self, path: Path) -> Path | None:
        """The workspace whose path names a component exactly ``.git``."""
        if self.L is None:
            return None
        base = self.L.workspace("x").parent.resolve()
        try:
            relative = path.relative_to(base)
        except ValueError:
            return None
        parts = relative.parts
        if len(parts) >= 2 and WO_ID_RE.fullmatch(parts[0]) and ".git" in parts[1:]:
            return base / parts[0]
        return None

    def workspaces(self, min_level: int = 1) -> list[ActiveOrder]:
        return [
            (order, level, push, workspace)
            for order, level, push, workspace in self.active
            if level >= min_level and workspace
        ]

    def ws_for(self, path: Path, min_level: int = 1) -> ActiveOrder | None:
        """The live order of this role whose workspace contains `path`, if any.

        Workspaces are derived from order IDs (`../<repo>.st/<WO>`), so the
        only candidate is the order named by the path; only its grant is
        verified (P-1). Everything else about authority is unchanged.
        """
        if self.L is None:
            return None
        base = self.L.workspace("x").parent
        try:
            wo = path.resolve().relative_to(base.resolve()).parts[0]
        except (ValueError, IndexError):
            return None
        for entry in self.active_for(wo):
            workspace = entry[3]
            if entry[1] >= min_level and workspace is not None and is_within(path, workspace):
                return entry
        return None

    def active_for(self, wo: str) -> list[ActiveOrder]:
        """This role's live order `wo`, verifying only that order's grant."""
        if self._active is not None:
            return [entry for entry in self._active if entry[0]["id"] == wo]
        if not (self.L and self.L.exists()):
            return []
        found: list[ActiveOrder] = []
        for order, _lease, level, push in live_orders(self.L, self.role, only=wo):
            if order["spec"]["role"] == self.role:
                found.append((order, level, push,
                              self.L.workspace(order["id"]) if level >= 1 else None))
        return found

    def no_ws_msg(self, what: str) -> str:
        held = (
            ", ".join(
                f"{order['id']} L{level}" for order, level, _, _ in self.active
            )
            or "no active order"
        )
        return (
            f"{what} is outside any workspace this role ({self.role}) may change "
            f"[{held}]. Report the need instead of working around it."
        )

    def protected_hit(self, path: Path) -> Path | None:
        for protected in self.protected:
            if is_within(path, protected):
                return protected
        return None

    def check_subagent(self, inp: JSON) -> str | None:
        """Every stage must run a guarded team agent on a dispatched order for its role.

        A stage on a generic agent (no guard hook) would escape authority
        entirely, so it is refused.
        """
        stages = inp.get("stages") or []
        if not stages:
            return "subagent call without stages"
        ledger = self.L
        if not (ledger and ledger.exists()):
            return "no ledger; the surgeon runs `st init` before the team can be dispatched"
        dispatched = {order["id"]: order for order, *_ in live_orders(ledger)}
        for stage in stages:
            agent = str(stage.get("role", ""))
            role = team_agent_role(agent)
            if not role or not is_role(role):
                return (
                    f"stage {stage.get('name')!r} uses agent {agent!r}; team work runs only on "
                    f"guarded {AGENT_PREFIX}<role> agents"
                )
            prompt = str(stage.get("prompt_template", ""))
            # A briefing opens with "# Work order WO-…"; that header, not a
            # mention (scope.out may name a parallel order), says which order a
            # prompt carries. Without any header, every live mention counts.
            headers = {
                order_id for order_id in BRIEFING_HEADER_RE.findall(prompt)
                if order_id in dispatched
            }
            carried = headers or {
                order_id for order_id in WO_ID_RE.findall(prompt) if order_id in dispatched
            }
            matching = [
                order_id for order_id in carried if dispatched[order_id]["spec"]["role"] == role
            ]
            if len(matching) != 1:
                return (
                    f"stage {stage.get('name')!r} must carry the briefing of exactly one order "
                    f"dispatched to {role} (run `st dispatch WO-…` and pass its output)"
                )
            if headers - {matching[0]}:
                return (
                    f"stage {stage.get('name')!r} is dispatched for {matching[0]}; pass only "
                    f"that order's briefing to {role}, without embedding the briefing of "
                    f"{', '.join(sorted(headers - {matching[0]}))}"
                )
        return None

    def blind_orders(self) -> list[tuple[Order, Path | None]]:
        """Orders that withhold paths from this role, with their workspaces.

        Blind lists only ever restrict, so they are read from every open
        lease's spec for this role without verifying its grant (P-1): an
        unverified order can only withhold more, never grant anything. The
        lease must still match the spec it was opened for.
        """
        if self._blind is None:
            found: list[tuple[Order, Path | None]] = []
            if self.L and self.L.exists():
                for wo, lease in Leases(self.L.root).open_leases().items():
                    if lease.get("role") != self.role:
                        continue
                    with contextlib.suppress(StError, OSError, ValueError, KeyError):
                        order = self.L.order(wo)
                        spec = order["spec"]
                        if spec.get("blind") and sha(spec) == lease.get("spec_sha"):
                            workspace = self.L.workspace(wo)
                            found.append((order, workspace if workspace.exists() else None))
            self._blind = found
        return self._blind

    def blind_hit(self, path: Path) -> tuple[str, str] | None:
        """F-13: an order may withhold paths (usually the implementation) from its role."""
        ledger = self.L
        if ledger is None:
            return None
        for order, workspace in self.blind_orders():
            for pattern in order["spec"].get("blind", []) or []:
                bases = [ledger.root] + ([workspace] if workspace else [])
                for base in bases:
                    try:
                        relative = path.resolve().relative_to(base.resolve()).as_posix()
                    except ValueError:
                        continue
                    stripped = pattern.rstrip("/")
                    if (
                        fnmatch.fnmatch(relative, stripped)
                        or relative == stripped
                        or relative.startswith(stripped + "/")
                    ):
                        return order["id"], pattern
        return None

    def blind_parent(self, path: Path) -> str | None:
        """A content search rooted above a withheld path could reveal it.

        An include or glob filter is not proof that withheld contents cannot
        match, so callers must narrow the search root outside the blind path.
        """
        ledger = self.L
        if ledger is None:
            return None
        for order, workspace in self.blind_orders():
            for pattern in order["spec"].get("blind", []) or []:
                bases = [ledger.root] + ([workspace] if workspace else [])
                for base in bases:
                    target = (base / pattern.split("*")[0]).resolve()
                    if is_within(target, path) and path.resolve() != target:
                        return (
                            f"{order['id']} is a blind order and a content search of {path} would "
                            f"include {pattern}. This is not a stop: search a narrower path "
                            "that does not contain the withheld path"
                        )
        return None

    # tools
    def check_source(self, raw: object, tool: str, inp: JSON) -> str | None:
        """E-3: an external tool runs only as a read-only source granted by an
        order this role holds, and only under a surgeon approval of that exact
        spec: under a standing order the copilot wrote the spec, so it could
        have granted the source itself.

        Non-AWS grants match the host-reported raw tool name exactly. There is
        no normalization or basename fallback between @server/tool and
        MCP:<tool> forms.
        """
        denied = (
            f"tool {raw!r} is not one the guard understands, so it is denied; the team "
            f"agents use {', '.join(sorted(KNOWN_TOOLS))}, plus read-only sources an "
            "approved order grants in inputs.sources"
        )
        grants = [
            (order, source)
            for order, _level, _push, _workspace in self.active
            if order.get("approval")
            for source in (order["spec"].get("inputs") or {}).get("sources", []) or []
            if isinstance(source, dict)
        ]
        if tool == AWS_TOOL:
            service = str(inp.get("service_name", "")).lower()
            operation = aws_op(inp.get("operation_name", ""))
            why = aws_op_refusal(operation)
            if why:
                return f"use_aws {service} {why}"
            if inp.get("positional_args"):
                return "use_aws with positional arguments (high-level commands) is never a source"
            for _order, source in grants:
                if (
                    normalize_tool(source["tool"]) != AWS_TOOL
                    or source.get("service") != service
                ):
                    continue
                if operation not in {aws_op(item) for item in source.get("operations", [])}:
                    continue
                if source.get("region") and source["region"] != inp.get("region"):
                    continue
                if source.get("profile") and source["profile"] != inp.get("profile_name"):
                    continue
                return None
            held = [
                order["id"]
                for order, source in grants
                if normalize_tool(source["tool"]) == AWS_TOOL
            ]
            return (
                f"use_aws {service} {operation} is not granted by any approved order "
                "this role holds"
                + (
                    f" (AWS sources in {', '.join(held)} do not cover it)"
                    if held
                    else ""
                )
            )
        for _order, source in grants:
            if source.get("readonly") is True and str(source["tool"]) == str(raw):
                return None
        return denied

    def check_read(self, inp: JSON, tool: str = "read") -> str | None:
        paths: list[tuple[object, bool]] = []
        listing = tool == "glob"
        for operation in inp.get("operations", []) or []:
            if operation.get("path"):
                paths.append((operation["path"], operation.get("mode") == "Directory"))
            paths.extend(
                (image_path, False)
                for image_path in operation.get("image_paths", []) or []
            )
        for key in ("path", "file_path", "filePath"):
            if inp.get(key):
                paths.append((inp[key], listing))
        if tool in ("grep", "code") and not paths:
            paths.append((str(self.cwd), False))
        for raw, is_listing in paths:
            path = self.resolve(raw, self.cwd)
            for secret in self.secrets:
                if (
                    is_within(path, secret)
                    and not path.name.endswith(".pub")
                    and path.name != "known_hosts"
                ):
                    return f"reading {path} is denied: signing and SSH key material"
            if is_listing:
                continue  # names are not contents
            hit = self.blind_hit(path)
            if hit:
                return (
                    f"{hit[0]} is a blind order: {hit[1]} is withheld so that you work from "
                    "the spec, not the implementation. Read the spec and public interface "
                    "instead; do not try to infer the withheld code"
                )
            if tool in ("grep", "code") and path.is_dir():
                why = self.blind_parent(path)
                if why:
                    return why
        return None

    def check_write_target(
        self, raw_path: object, base: Path, what: str = "write"
    ) -> str | None:
        """Check both the lexical target name and its canonical destination."""
        lexical = self.lexical_path(raw_path, base)
        return self.check_write_path(self.resolve(raw_path, base), what, lexical)

    def check_write_path(
        self, path: Path, what: str = "write", lexical: Path | None = None
    ) -> str | None:
        if str(path) == "/dev/null":
            return None
        shown = lexical or path
        for candidate in (shown, path):
            workspace = self.workspace_git_metadata_hit(candidate)
            if workspace is not None:
                return (
                    f"{what} to {shown} is denied: any .git path inside {workspace} is "
                    "workspace Git metadata, and git metadata runs on the host. Change "
                    "project files such as .gitignore or .gitmodules instead."
                )
        hit = self.protected_hit(path)
        if not hit and LEDGER_DIRNAME in path.parts:
            hit = path
        if hit:
            return (
                f"{what} to {path} is denied: {hit} is control-plane state (ledger, trust "
                "root, agent configs, or the st tool). File through `st` commands."
            )
        if self.ws_for(path):
            return None
        return self.no_ws_msg(f"{what} to {path}")


def guard_decide(role: str, event: ToolEvent) -> str | None:
    raw = event.tool_name
    tool = normalize_tool(raw)
    inp: JSON = event.tool_input or {}
    guard = Guard(role, event)
    if guard.context_refusal:
        return guard.context_refusal
    if tool not in KNOWN_TOOLS:
        # Fail closed: a tool the guard does not understand may write, unless
        # an order this role holds grants it as a read-only source (E-3).
        return guard.check_source(raw, tool, inp)
    if (
        tool == "code"
        and inp.get("operation") in CODE_WRITE_OPS
        and inp.get("dry_run") is not True
    ):
        target = (
            inp.get("file_path")
            or inp.get("filePath")
            or inp.get("path")
            or str(guard.cwd)
        )
        return guard.check_write_target(
            target, guard.cwd, f"code {inp.get('operation')}"
        )
    if tool in ("read", "grep", "glob", "code"):
        return guard.check_read(inp, tool)
    if tool == "write":
        paths = [inp.get(key) for key in ("path", "file_path", "filePath") if inp.get(key)]
        if not paths:
            return "write without a path"
        for raw_path in paths:
            why = guard.check_write_target(raw_path, guard.cwd)
            if why:
                return why
        return None
    if tool == "shell":
        working_dir = inp.get("working_dir")
        return guard.check_shell(
            str(inp.get("command", "")),
            guard.resolve(working_dir, guard.cwd) if working_dir else guard.cwd,
        )
    if tool == "subagent":
        if role != "copilot":
            return "only the copilot dispatches subagents"
        return guard.check_subagent(inp)
    return None  # web_search, web_fetch, todo_list, summary: no local side effects


def cmd_guard(args: argparse.Namespace) -> int:
    return guard_main(args.role, getattr(args, "host", DEFAULT_HOST))


def guard_main(role: str | None, host_name: str = DEFAULT_HOST) -> int:
    """Run the guard for one hook event from `host_name` on stdin.

    Returns the host's allow or block exit code. Every failure fails closed
    to a block: a host the guard does not know, an unparseable event, a
    missing role, or any internal error.
    """
    clear_ledger_cache()  # one answer per call, even when tests run many in one process
    host = HOSTS.get(host_name)
    if host is None:
        response = Response(KiroHost.block_exit, stderr=block_message(
            f"unknown host {host_name!r}; known: {', '.join(sorted(HOSTS))}"))
    elif host is CursorHost:
        try:
            response = cursor_handle(sys.stdin.read(), role, guard_decide)
        except Exception as error:  # fail closed
            response = CursorHost.respond(
                f"guard error, failing closed: {type(error).__name__}: {error}")
    else:
        try:
            if not role:
                raise StError(f"the {host_name} hook must pass --role")
            why = guard_decide(role, host.parse(sys.stdin.read()))
        except Exception as error:  # fail closed
            why = f"guard error, failing closed: {type(error).__name__}: {error}"
        response = host.respond(why)
    if response.stdout:
        print(response.stdout)
    if response.stderr:
        print(response.stderr, file=sys.stderr)
    return response.exit
