"""What the team leaves around a project, and taking it away again (goal: optional).

Inside the project there is only the ledger (.surgical-team/, committed by
choice). Around it, dispatch adds a sibling ../<repo>.st/ directory of
worktrees and st/WO-* branches; installs add user-level agents and hooks.
None of it is needed by the project itself, and all of it can be removed:

  verdicts and cancel   remove a closed order's worktree when it is clean
  st prune              removes closed orders' leftover worktrees (dirty ones
                        with --force) and their branches once nothing is lost
  st uninstall          removes the user-level agents, hooks, and /st command
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from ..authority import verdict_for
from ..gitutil import git, worktree_git
from ..guard.hosts import cursor_dir
from ..ledger import Ledger
from ..model import AGENT_PREFIX, TERMINAL, StError
from ..roles import TEAM_ROOT, team_roles
from ..signing import verify
from ..types import JSON, State
from .install import cursor_command_path, is_team_hook

BRANCH_RE = re.compile(r"^st/(WO-\d{8}-\d{3})(?:-|$)")


def _dirty(ledger: Ledger, workspace: Path) -> bool:
    return bool(worktree_git(["status", "--porcelain"], ledger, workspace, check=False))


def release_workspace(ledger: Ledger, wo: str) -> str | None:
    """Remove a closed order's worktree if nothing would be lost; say what happened."""
    workspace = ledger.workspace(wo)
    if not workspace.exists():
        return None
    if _dirty(ledger, workspace):
        return (f"kept {workspace}: it has uncommitted changes (at L1 that is the work "
                "itself); `st prune --force` removes it once you have what you need")
    git(["worktree", "remove", str(workspace)], ledger.root)
    _remove_empty_parent(workspace)
    return f"removed {workspace} (its branch stays until `st prune`)"


def _remove_empty_parent(workspace: Path) -> None:
    parent = workspace.parent
    if parent.is_dir() and not any(parent.iterdir()):
        parent.rmdir()


def team_branches(ledger: Ledger) -> dict[str, list[str]]:
    """st/* branches by order ID."""
    names = git(["for-each-ref", "--format=%(refname:short)", "refs/heads/st/"],
                ledger.root, check=False).split()
    found: dict[str, list[str]] = {}
    for name in names:
        match = BRANCH_RE.match(name)
        if match:
            found.setdefault(match.group(1), []).append(name)
    return found


def footprint(ledger: Ledger) -> JSON:
    """Counts for st doctor: worktrees, closed ones left over, and st/* branches."""
    base = ledger.workspace("x").parent
    workspaces = sorted(p.name for p in base.iterdir() if p.is_dir()) if base.is_dir() else []
    closed = []
    for wo in workspaces:
        try:
            if ledger.order(wo)["state"] in TERMINAL:
                closed.append(wo)
        except (StError, OSError, KeyError, ValueError):
            closed.append(wo)
    return {"base": str(base), "workspaces": workspaces, "closed": closed,
            "branches": sum(len(v) for v in team_branches(ledger).values())}


def _merged(ledger: Ledger, branch: str, into: str) -> bool:
    return not git(["rev-list", "--max-count=1", branch, f"^{into}"], ledger.root, check=False)


def _verified_terminal_state(ledger: Ledger, wo: str) -> tuple[State | None, str | None]:
    """Return a state only when destructive cleanup has signed closure evidence.

    Order state is shared, unsigned bookkeeping. A forged terminal value must
    never authorize deleting the order's workspace or branch.
    """
    try:
        order = ledger.order(wo)
        state = order["state"]
        if state in ("accepted", "rejected"):
            if verdict_for(ledger, order) != state:
                return None, (
                    f"ledger says {state}, but no matching surgeon-signed verdict verifies"
                )
        elif state == "cancelled":
            ok, why = verify(
                order.get("cancellation"), {"kind": "cancel", "order": order["id"]}
            )
            if not ok:
                return None, (
                    "ledger says cancelled, but its surgeon-signed cancellation does not "
                    f"verify ({why})"
                )
        return state, None
    except (AttributeError, KeyError, OSError, StError, TypeError, ValueError) as error:
        return None, f"could not verify terminal state from its order record ({error})"


def cmd_prune(args: argparse.Namespace) -> None:
    ledger = Ledger.at()
    ledger.require()
    into = args.into or git(["symbolic-ref", "--short", "HEAD"], ledger.root, check=False) \
        or "HEAD"
    act = not args.dry_run
    actions: list[str] = []
    states: dict[str, tuple[State | None, str | None]] = {}

    def state(wo: str) -> tuple[State | None, str | None]:
        if wo not in states:
            states[wo] = _verified_terminal_state(ledger, wo)
        return states[wo]

    base = ledger.workspace("x").parent
    kept: set[str] = set()
    for workspace in sorted(base.iterdir()) if base.is_dir() else []:
        wo = workspace.name
        current, unverified = state(wo)
        if current not in TERMINAL:
            kept.add(wo)
            if unverified:
                actions.append(f"keep {workspace}: {unverified}")
            continue
        if _dirty(ledger, workspace) and not args.force:
            kept.add(wo)
            actions.append(f"keep {workspace}: uncommitted changes (--force removes them)")
            continue
        actions.append(f"remove worktree {workspace}")
        if act:
            git(["worktree", "remove", "--force", str(workspace)], ledger.root)
    if act:
        git(["worktree", "prune"], ledger.root, check=False)
    for wo, branches in sorted(team_branches(ledger).items()):
        current, unverified = state(wo)
        for branch in branches:
            if unverified:
                actions.append(f"keep {branch}: {unverified}")
                continue
            if current in ("rejected", "cancelled"):
                why = str(current)
            elif current == "accepted" and _merged(ledger, branch, into):
                why = f"accepted and merged into {into}"
            else:
                if current == "accepted":
                    actions.append(f"keep {branch}: accepted but not merged into {into}")
                continue
            if wo in kept:
                actions.append(f"keep {branch}: its worktree was kept")
                continue
            actions.append(f"delete branch {branch} ({why})")
            if act:
                git(["branch", "-D", branch], ledger.root)
    if act and base.is_dir() and not any(base.iterdir()):
        base.rmdir()
        actions.append(f"removed empty {base}")
    for line in actions or ["nothing to prune"]:
        print(("would " if args.dry_run and not line.startswith("keep") else "") + line)


def _remove(path: Path, removed: list[str]) -> None:
    if path.is_file():
        path.unlink()
        removed.append(str(path))


def uninstall_kiro(args: argparse.Namespace) -> list[str]:
    destination = Path(args.dir).expanduser() if args.dir else Path.home() / ".kiro" / "agents"
    removed: list[str] = []
    for role in team_roles(TEAM_ROOT):
        _remove(destination / f"{AGENT_PREFIX}{role}.json", removed)
    return removed


def uninstall_cursor(args: argparse.Namespace) -> list[str]:
    destination = Path(args.dir).expanduser() if args.dir else cursor_dir() / "agents"
    hooks_path = Path(args.hooks).expanduser() if args.hooks else cursor_dir() / "hooks.json"
    removed: list[str] = []
    if hooks_path.exists():
        try:
            config = json.loads(hooks_path.read_text())
        except ValueError as error:
            raise StError(f"{hooks_path} is not valid JSON ({error}); fix it by hand first") \
                from error
        hooks = config.get("hooks") if isinstance(config, dict) else None
        if not isinstance(hooks, dict):
            raise StError(f"{hooks_path}: `hooks` is not an object; fix it by hand first")
        kept = {event: [e for e in entries if not is_team_hook(e)]
                for event, entries in hooks.items() if isinstance(entries, list)}
        if kept != hooks:
            config["hooks"] = {event: entries for event, entries in kept.items() if entries}
            hooks_path.write_text(json.dumps(config, indent=2) + "\n")
            removed.append(f"st guard entries in {hooks_path} (other hooks kept)")
    for role in team_roles(TEAM_ROOT):
        _remove(destination / f"{AGENT_PREFIX}{role}.md", removed)
    _remove(cursor_command_path(args), removed)
    return removed


def cmd_uninstall(args: argparse.Namespace) -> None:
    hosts = ["kiro", "cursor"] if args.host == "all" else [args.host]
    removed: list[str] = []
    for host in hosts:
        removed += uninstall_kiro(args) if host == "kiro" else uninstall_cursor(args)
    for line in removed or ["nothing installed"]:
        print(f"removed {line}" if removed else line)
    print("ledgers are untouched; to drop the team from a project: st prune, then "
          "git rm -r .surgical-team")
