"""Argument parsing and the entry point."""
from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING

from .commands.doctor import cmd_doctor
from .commands.footprint import cmd_prune, cmd_uninstall
from .commands.install import cmd_install
from .commands.migrate import cmd_migrate
from .commands.orders import cmd_brief, cmd_dispatch, cmd_draft, cmd_report, cmd_revise
from .commands.records import cmd_check, cmd_journal, cmd_list, cmd_reclaim, cmd_show, cmd_verify
from .commands.surgeon import (
    _verdict,
    cmd_approve,
    cmd_cancel,
    cmd_decide,
    cmd_grant,
    cmd_init,
    cmd_revoke,
    cmd_setup,
)
from .guard.core import cmd_guard
from .model import LEVELS, VERSION, StError
from .status import cmd_status
from .types import State

if TYPE_CHECKING:
    Command = Callable[[argparse.Namespace], int | None]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="st", description="Surgical team control plane")
    parser.add_argument("--version", action="version", version=f"st {VERSION}")
    subparsers = parser.add_subparsers(dest="cmd", required=True)

    def add(name: str, function: Command, help_text: str) -> argparse.ArgumentParser:
        subparser = subparsers.add_parser(name, help=help_text)
        subparser.set_defaults(fn=function)
        return subparser

    command_parser = add("draft", cmd_draft, "file a new order from JSON on stdin")
    command_parser.add_argument("--file")
    command_parser = add("revise", cmd_revise, "replace an order's spec; returns it to drafted")
    command_parser.add_argument("order")
    command_parser.add_argument("--file")
    command_parser.add_argument("--note")
    command_parser = add(
        "dispatch", cmd_dispatch, "dispatch an approved order; prints the briefing"
    )
    command_parser.add_argument("order")
    command_parser.add_argument("--allow-overlap", action="store_true")
    command_parser = add("brief", cmd_brief, "print an order's briefing")
    command_parser.add_argument("order")
    command_parser = add(
        "report", cmd_report, "file the report for the current attempt (JSON on stdin)"
    )
    command_parser.add_argument("order")
    command_parser.add_argument("--file")
    command_parser = add("check", cmd_check, "run the order's executable acceptance checks")
    command_parser.add_argument("order")
    command_parser = add(
        "reclaim", cmd_reclaim, "return a stuck dispatched order for re-dispatch"
    )
    command_parser.add_argument("order")
    command_parser.add_argument("--reason", required=True)
    add("journal", cmd_journal, "append a session journal entry (markdown on stdin)")
    command_parser = add("show", cmd_show, "show an order with its authority, report, checks")
    command_parser.add_argument("order")
    command_parser = add("list", cmd_list, "list orders")
    command_parser.add_argument("--state")
    add("status", cmd_status, "render STATUS.md and print it")
    add("verify", cmd_verify, "verify every signature in the ledger")
    command_parser = add("guard", cmd_guard, "pre-tool hook (reads the host event on stdin)")
    command_parser.add_argument(
        "--role", help="the agent's role (required for kiro; cursor binds roles per session)")
    command_parser.add_argument(
        "--host", default="kiro", help="host hook format: kiro (default) or cursor")

    command_parser = add("setup", cmd_setup, "[surgeon] configure the signing key")
    command_parser.add_argument("--key", required=True)
    command_parser.add_argument("--identity", required=True)
    command_parser.add_argument(
        "--allow-unencrypted",
        action="store_true",
        help="accept a key with no passphrase (test setups only)",
    )
    command_parser = add("init", cmd_init, "[surgeon] create the ledger in this repository")
    command_parser.add_argument(
        "--default-standing",
        action="store_true",
        help="also file a signed standing order: L0 work needs no approval",
    )
    command_parser = add("approve", cmd_approve, "[surgeon] approve a drafted order")
    command_parser.add_argument("order")
    command_parser.add_argument("--level", choices=sorted(LEVELS))
    command_parser.add_argument("--push", action="store_true")
    command_parser.add_argument(
        "--for",
        dest="valid_for",
        type=int,
        metavar="MINUTES",
        help="how long the approval may be used (default max(60, 3x budget))",
    )
    verdicts: tuple[tuple[str, State], ...] = (
        ("accept", "accepted"),
        ("reject", "rejected"),
        ("defer", "deferred"),
    )
    for name, verdict in verdicts:
        def run_verdict(args: argparse.Namespace, selected: State = verdict) -> None:
            _verdict(args, selected)

        command_parser = add(
            name, run_verdict, f"[surgeon] {name} reported orders"
        )
        command_parser.add_argument("orders", nargs="+")
        command_parser.add_argument("-m", "--message")
    command_parser = add("cancel", cmd_cancel, "[surgeon] cancel an order")
    command_parser.add_argument("order")
    command_parser.add_argument("-m", "--message")
    command_parser = add("decide", cmd_decide, "[surgeon] record a decision")
    command_parser.add_argument("--title", required=True)
    command_parser.add_argument("--decision", required=True)
    command_parser.add_argument("--why")
    command_parser.add_argument("--consequence", action="append")
    command_parser.add_argument("--rejected", action="append")
    command_parser.add_argument("--scope")
    command_parser.add_argument("--context")
    command_parser.add_argument("--supersedes")
    command_parser.add_argument("--expires")
    command_parser.add_argument(
        "--dissent", action="append",
        help="an objection raised and overruled (repeatable); signed with the decision")
    command_parser = add("grant", cmd_grant, "[surgeon] issue a standing order")
    command_parser.add_argument("--role", required=True)
    command_parser.add_argument("--max", required=True)
    command_parser.add_argument("--scope", required=True)
    command_parser.add_argument("--budget", type=int, default=30)
    command_parser.add_argument("--expires")
    command_parser = add("revoke", cmd_revoke, "[surgeon] revoke a decision or standing order")
    command_parser.add_argument("decision")
    command_parser.add_argument("-m", "--message")
    command_parser = add(
        "install", cmd_install, "[surgeon] write guarded st-<role> agents for a host")
    command_parser.add_argument("--host", default="kiro", choices=["kiro", "cursor"],
                                help="kiro (default): ~/.kiro/agents; cursor: ~/.cursor/agents "
                                     "plus the guard in ~/.cursor/hooks.json")
    command_parser.add_argument("--dir", help="agents destination (overrides the host default)")
    command_parser.add_argument("--hooks", help="cursor hooks.json to merge into "
                                                "(default ~/.cursor/hooks.json)")
    command_parser.add_argument("--commands", help="cursor commands directory for /st "
                                                   "(default ~/.cursor/commands)")
    command_parser = add("uninstall", cmd_uninstall,
                         "[surgeon] remove the user-level agents, hooks, and /st command")
    command_parser.add_argument("--host", default="all", choices=["kiro", "cursor", "all"])
    command_parser.add_argument("--dir", help="agents directory (overrides the host default)")
    command_parser.add_argument("--hooks", help="cursor hooks.json (default ~/.cursor/hooks.json)")
    command_parser.add_argument("--commands", help="cursor commands directory "
                                                   "(default ~/.cursor/commands)")
    command_parser = add("prune", cmd_prune, "[surgeon] remove closed orders' worktrees and "
                                             "branches that no longer hold unmerged work")
    command_parser.add_argument("--dry-run", action="store_true")
    command_parser.add_argument(
        "--force", action="store_true",
        help="also remove closed orders' worktrees with uncommitted changes")
    command_parser.add_argument("--into", help="branch that accepted work merges into "
                                               "(default: the main checkout's branch)")
    command_parser = add("migrate", cmd_migrate, "[surgeon] upgrade the ledger's on-disk format")
    command_parser.add_argument("--dry-run", action="store_true")
    command_parser = add("doctor", cmd_doctor, "check the environment the team depends on")
    command_parser.add_argument("--quick", action="store_true", help="skip the latency sample")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return run(args)


def run(args: argparse.Namespace) -> int:
    try:
        command: Command = args.fn
        result = command(args)
    except StError as error:
        print(f"st: {error}", file=sys.stderr)
        return 1
    return result or 0
