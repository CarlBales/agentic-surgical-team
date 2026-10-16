"""The guard's shell checks: commands, programs, git, and push."""
from __future__ import annotations

import ast
import os
import re
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Literal, cast, overload

from ..gitutil import git, is_within
from ..guard.shell import (
    FILE_MUTATORS,
    GIT_ALWAYS_DENY,
    GIT_DIR_OPTS,
    GIT_HISTORY_OPS,
    GIT_READ,
    GIT_WORKTREE_OPS,
    GUARDED_ENV,
    INPLACE_EDITORS,
    INTERPRETERS,
    READ_REDIRECTS,
    READONLY_PROGS,
    SHELLS,
    STDIN_PATHS,
    UNRESOLVED,
    WRAPPERS,
    WRITE_REDIRECTS,
    shell_inline,
    shell_reads_stdin,
    shell_segments,
    SHELL_KEYWORDS,
    substitution_reason,
)
from ..model import LEDGER_DIRNAME, SPECIALIST_ST_CMDS, SURGEON_CMDS, StError, sha
from ..signing import config_dir, verify

if TYPE_CHECKING:
    from ..ledger import Ledger
    from ..types import Order

    ActiveOrder = tuple[Order, int, bool, Path | None]


# A speed bump for well-behaved models, not a security boundary: the guard can
# recognize these host CLIs when they appear in the shell command it parses, but
# a build script can still start one. The network-disabled sandbox is the boundary.
AGENT_HOST_CLIS = frozenset({
    "agent",
    "cursor-agent",
    "cursor",
    "kiro-cli",
    "kiro",
    "q",
    "claude",
    "codex",
    "gemini",
    "aider",
    "goose",
    "opencode",
    "copilot",
    "@anthropic-ai/claude-code",
    "@openai/codex",
    "@google/gemini-cli",
})


class GuardShell:
    """Shell checks, mixed into Guard. Uses Guard's state (role, L, active, secrets, protected)."""

    role: str
    home: Path
    L: Ledger | None
    secrets: list[Path]
    protected: list[Path]

    if TYPE_CHECKING:
        @property
        def active(self) -> list[ActiveOrder]: ...

        def resolve(self, path: object, base: Path) -> Path: ...

        def ws_for(self, path: Path, min_level: int = 1) -> ActiveOrder | None: ...

        def check_write_target(
            self, raw_path: object, base: Path, what: str = "write"
        ) -> str | None: ...

        def blind_hit(self, path: Path) -> tuple[str, str] | None: ...

        def blind_parent(self, path: Path) -> str | None: ...

        def protected_hit(self, path: Path) -> Path | None: ...

        def no_ws_msg(self, what: str) -> str: ...

    def check_shell(self, cmd: str, cwd: Path) -> str | None:
        return self._check_shell(cmd, cwd)[0]

    def _check_shell(self, cmd: str, cwd: Path) -> tuple[str | None, Path]:
        """(refusal or None, working directory after the command)."""
        try:
            segments = shell_segments(cmd)
        except ValueError as error:
            return f"could not parse the command ({error}); simplify it", cwd
        marks = [LEDGER_DIRNAME, str(config_dir()), "allowed_signers", ".kiro/agents",
                 ".cursor/agents", ".cursor/hooks"]
        if any(mark in cmd for mark in marks):
            programs = [str(self.program(self.strip_redirects(segment)[0])[0] or "")
                        for segment in segments]
            for raw in programs:
                program_name = Path(raw).name
                if program_name in ("sed", "find") or (
                    program_name not in READONLY_PROGS and program_name not in ("st", "git")
                ):
                    variable = next((p for p in programs if p.startswith("$")), None)
                    if variable:
                        # Seen live: `ST=/path/bin/st; $ST report ...` was refused and the
                        # agent gave up. Say how to succeed; the answer is still a refusal.
                        return (
                            "this command references control-plane state, and the guard "
                            f"cannot tell which program {variable} names; call `st` by name "
                            "or by its literal path (for example `/path/to/bin/st report "
                            "...`), not through a variable, and retry",
                            cwd,
                        )
                    return (
                        "this command references control-plane state; only `st` and "
                        "read-only viewers may touch it",
                        cwd,
                    )
        current = cwd.resolve()
        unsafe = substitution_reason(cmd)
        if unsafe:
            return (
                f"{unsafe} is denied: the guard cannot see the command it runs. Put it in a "
                "script in the workspace and run that",
                current,
            )
        for segment in segments:
            if segment and segment[0] in SHELL_KEYWORDS:
                return (
                    f"`{segment[0]}` introduces shell control flow the guard does not model. "
                    "Put loops, conditionals, and the like in a script in the workspace and "
                    "run it (e.g. `bash build.sh`); chains with ;, &&, ||, and | are fine",
                    current,
                )
            words, targets = self.strip_redirects(segment)
            for redirect_target in targets:
                if UNRESOLVED.search(redirect_target):
                    return (
                        f"redirect target {redirect_target!r} cannot be resolved by the guard",
                        current,
                    )
                why = self.check_write_target(redirect_target, current, "redirect")
                if why:
                    return why, current
            program, args, environment, wrappers = self.program(words, full=True)
            for variable in environment:
                if variable in GUARDED_ENV:
                    return (
                        f"setting {variable} is denied: it redirects git or st away from "
                        "the order",
                        current,
                    )
            if "env -S" in wrappers:
                return "env -S splits a string into a command the guard cannot see", current
            if program is None:
                continue
            name = Path(program).name or program
            if name in ("export", "declare", "typeset", "set", "unset") and any(
                arg.split("=")[0] in GUARDED_ENV for arg in args
            ):
                return "changing GIT_* or ST_* variables is denied", current
            if name in ("cd", "pushd"):
                directory_target = next(
                    (arg for arg in args if not arg.startswith("-") or arg == "-"), None
                )
                if directory_target is None:
                    current = self.home
                elif directory_target == "-" or UNRESOLVED.search(directory_target):
                    return (
                        f"`{name} {directory_target}` cannot be resolved by the guard; use a "
                        "literal path",
                        current,
                    )
                else:
                    current = self.resolve(directory_target, current)
                continue
            if name == "popd":
                return (
                    "popd cannot be resolved by the guard; use `cd` with a literal path",
                    current,
                )
            why = self.agent_host_refusal(name, args)
            if why:
                return why, current
            if "xargs" in wrappers and name not in READONLY_PROGS:
                return f"`xargs {name}` hides its arguments from the guard", current
            if re.search(r"\s", program):
                return (
                    f"program {program!r} contains whitespace; the guard cannot resolve it",
                    current,
                )
            why = self.hidden_code(name, args, wrappers)
            if why:
                return why, current
            if name == "eval":
                # S-1: eval runs its arguments in *this* shell, so a `cd` inside
                # it moves every later segment. Check the joined text and carry
                # its working directory forward.
                why, current = self._check_shell(" ".join(args), current)
                if why:
                    return f"inside eval: {why}", current
                continue
            if name in SHELLS:
                inner = shell_inline(args)
                if inner is not None:
                    why = self.check_shell(inner, current)  # child shell: cwd does not leak
                    if why:
                        return why, current
                    continue
            if name in READONLY_PROGS or name == "git":
                file_args = [arg for arg in args if not arg.startswith("-")]
                for arg in file_args:
                    if "/" not in arg and not (current / arg).exists():
                        continue
                    hit = self.blind_hit(self.resolve(arg, current))
                    if hit:
                        return f"{hit[0]} is a blind order: {hit[1]} is withheld", current
                searcher = name in ("rg", "grep", "egrep", "fgrep") or (
                    name == "git" and file_args[:1] == ["grep"]
                )
                if searcher:
                    directories = [
                        self.resolve(arg, current)
                        for arg in file_args
                        if (current / arg).is_dir() or Path(os.path.expanduser(arg)).is_dir()
                    ] or [current]
                    for directory in directories:
                        why = self.blind_parent(directory)
                        if why:
                            return why, current
            why = self.check_program(name, program, args, current)
            if why:
                return why, current
        return None, current

    @staticmethod
    def _agent_cli_token(token: str) -> str | None:
        """The exact CLI/package named by one command token, allowing a version."""
        for candidate in sorted(AGENT_HOST_CLIS, key=len, reverse=True):
            if token == candidate or token.startswith(candidate + "@"):
                return candidate
        return None

    def _agent_cli_invocation(self, name: str, args: Sequence[str]) -> str | None:
        """Recognize a direct host or package-runner invocation already tokenized."""
        direct = self._agent_cli_token(name)
        if direct:
            if direct == "q" and args[:1] != ["chat"]:
                return None
            return direct

        runner_args: Sequence[str]
        if name in ("npx", "bunx", "uvx"):
            runner_args = args
        elif name == "pnpm":
            positional = [index for index, arg in enumerate(args) if not arg.startswith("-")]
            if not positional or args[positional[0]] != "dlx":
                return None
            runner_args = args[positional[0] + 1 :]
        else:
            return None
        package_at = next(
            (index for index, arg in enumerate(runner_args) if not arg.startswith("-")),
            None,
        )
        if package_at is None:
            return None
        package = self._agent_cli_token(runner_args[package_at])
        if package == "q" and runner_args[package_at + 1 : package_at + 2] != ["chat"]:
            return None
        return package

    def _literal_agent_cli(self, node: ast.AST) -> str | None:
        """An agent CLI in a literal process-launch argument inside Python -c."""
        commands: list[list[str]] = []
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            try:
                commands.extend(shell_segments(node.value))
            except ValueError:
                return None
        elif isinstance(node, (ast.List, ast.Tuple)):
            words: list[str] = []
            for item in node.elts:
                if not isinstance(item, ast.Constant) or not isinstance(item.value, str):
                    return None
                words.append(item.value)
            commands.append(words)
        for words in commands:
            program, cli_args = self.program(words)
            if program is None:
                continue
            found = self._agent_cli_invocation(Path(program).name or program, cli_args)
            if found:
                return found
        return None

    def _python_agent_cli(self, name: str, args: Sequence[str]) -> str | None:
        """Recognize literal os/subprocess launches in inline Python code.

        This closes the common ``python -c os.system(...)`` spelling without
        pretending to interpret arbitrary code. A script remains part of the
        documented sandbox boundary.
        """
        if name not in ("python", "python3") or "-c" not in args:
            return None
        index = args.index("-c")
        if index + 1 >= len(args):
            return None
        try:
            tree = ast.parse(args[index + 1])
        except (SyntaxError, ValueError):
            return None
        launchers = {
            "system", "popen", "Popen", "run", "call", "check_call",
            "check_output", "execv", "execve", "execvp", "execvpe",
            "spawnl", "spawnlp", "spawnv", "spawnvp",
        }
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            function = node.func
            called = (
                function.attr if isinstance(function, ast.Attribute)
                else function.id if isinstance(function, ast.Name)
                else ""
            )
            if called not in launchers:
                continue
            for argument in node.args:
                found = self._literal_agent_cli(argument)
                if found:
                    return found
        return None

    def agent_host_refusal(self, name: str, args: Sequence[str]) -> str | None:
        invoked = self._agent_cli_invocation(name, args) or self._python_agent_cli(name, args)
        if not invoked:
            return None
        return (
            f"`{invoked}` is an agent-host CLI; starting another agent host is denied "
            "for every team role. Continue in this guarded session instead"
        )

    def hidden_code(
        self, name: str, args: Sequence[str], wrappers: Sequence[str]
    ) -> str | None:
        """S-1: constructs that run code the guard never sees as a command line."""
        if name in ("source", "."):
            return (
                f"`{name}` runs a file in the current shell, out of the guard's sight; "
                "run the script with `bash FILE` inside the workspace instead"
            )
        if name in ("trap", "alias", "function"):
            return f"`{name}` defines code to run later, which the guard cannot check"
        if name in SHELLS and shell_inline(args) is None and shell_reads_stdin(args):
            return (
                f"`{name}` reading commands from stdin is denied: the guard cannot see "
                "them. Write the script to a file in the workspace and run that"
            )
        if (
            name in INTERPRETERS
            and INTERPRETERS[name] not in args
            and not any(
                arg
                for arg in args
                if not arg.startswith("-") and arg not in STDIN_PATHS
            )
        ):
            return (
                f"`{name}` reading code from stdin is denied: the guard cannot see it. "
                "Write it to a file in the workspace and run that"
            )
        return None

    def strip_redirects(self, segment: Sequence[str]) -> tuple[list[str], list[str]]:
        words: list[str] = []
        targets: list[str] = []
        index = 0
        while index < len(segment):
            token = segment[index]
            if token in WRITE_REDIRECTS:
                if words and words[-1].isdigit():
                    words.pop()
                if index + 1 < len(segment):
                    target = segment[index + 1]
                    if not (target.isdigit() or target == "-"):
                        targets.append(target)
                index += 2
                continue
            if token in READ_REDIRECTS:
                if words and words[-1].isdigit():
                    words.pop()
                index += 2
                continue
            words.append(token)
            index += 1
        return words, targets

    @overload
    def program(
        self, segment: Sequence[str], full: Literal[False] = False
    ) -> tuple[str | None, list[str]]: ...

    @overload
    def program(
        self, segment: Sequence[str], full: Literal[True]
    ) -> tuple[str | None, list[str], list[str], list[str]]: ...

    def program(
        self, segment: Sequence[str], full: bool = False
    ) -> (
        tuple[str | None, list[str]]
        | tuple[str | None, list[str], list[str], list[str]]
    ):
        """Find the program in a segment, past VAR=x prefixes and wrappers."""
        index = 0
        environment: list[str] = []
        wrappers: list[str] = []
        assignment = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=")
        while index < len(segment):
            match = assignment.match(segment[index])
            if match is None:
                break
            environment.append(match.group(1))
            index += 1
        wrapper_names = WRAPPERS | {"timeout"}
        option_values = {
            "env": {"-u", "--unset", "-C", "--chdir"},
            "exec": {"-a"},
            "nice": {"-n", "--adjustment"},
            "time": {"-f", "--format", "-o", "--output"},
            "timeout": {"-k", "--kill-after", "-s", "--signal"},
            "xargs": {
                "-a", "--arg-file", "-E", "--eof", "-I", "--replace",
                "-L", "--max-lines", "-n", "--max-args", "-P", "--max-procs",
                "-s", "--max-chars",
            },
        }
        while index < len(segment) and Path(segment[index]).name in wrapper_names:
            wrapper = Path(segment[index]).name
            wrappers.append(wrapper)
            index += 1
            while index < len(segment):
                word = segment[index]
                match = assignment.match(word)
                if match:
                    environment.append(match.group(1))
                    index += 1
                    continue
                if word == "--":
                    index += 1
                    break
                if not word.startswith("-"):
                    break
                option = word.split("=", 1)[0]
                if wrapper == "env" and re.match(r"^(-[A-Za-z]*S|--split-string)", word):
                    wrappers.append("env -S")
                index += 1
                if option in option_values.get(wrapper, set()) and "=" not in word:
                    index += 1
            if wrapper == "timeout" and index < len(segment):
                index += 1  # the duration precedes the wrapped command
        if index < len(segment):
            program = segment[index]
            args = list(segment[index + 1 :])
        else:
            program = None
            args = []
        if full:
            return program, args, environment, wrappers
        return program, args

    def outward_arg(self, args: Sequence[str], current: Path) -> str | None:
        """An argument that points into the main checkout or control plane.

        From inside a workspace, the only reason to name the main checkout is
        to change it; the workspace holds its own copy of every file.
        """
        for arg in args:
            candidates = ([arg] if not arg.startswith("-") else []) + (
                [arg.split("=", 1)[1]] if "=" in arg else []
            )
            for candidate in candidates:
                if "/" not in candidate and not candidate.startswith("~"):
                    continue
                if UNRESOLVED.search(candidate):
                    return f"argument {candidate!r} cannot be resolved by the guard"
                path = self.resolve(candidate, current)
                if self.L and is_within(path, self.L.root):
                    return (
                        f"argument {candidate} points into the main checkout; from a workspace, "
                        "work on the workspace copy"
                    )
                if self.protected_hit(path) or any(
                    is_within(path, secret) for secret in self.secrets
                ):
                    return f"argument {candidate} points at control-plane state or key material"
        return None

    def check_program(
        self, name: str, program: str, args: list[str], current: Path
    ) -> str | None:
        in_workspace = self.ws_for(current)
        if name in ("sudo", "su", "doas"):
            return f"{name} is denied: privilege escalation is outside every authority level"
        if name in ("ssh-keygen", "ssh-add", "ssh-agent"):
            return f"{name} is denied: agents never touch signing keys"
        if name == "st" or program.endswith("/st"):
            positional = [arg for arg in args if not arg.startswith("-")]
            subcommand = positional[0] if positional else ""
            if subcommand in SURGEON_CMDS:
                return (
                    f"`st {subcommand}` is surgeon-only. Ask the surgeon to run it in their own "
                    "terminal; it is signed with their key."
                )
            if self.role != "copilot" and subcommand not in SPECIALIST_ST_CMDS:
                return (
                    f"`st {subcommand}` belongs to the copilot; specialists may run "
                    f"{', '.join(sorted(SPECIALIST_ST_CMDS))}"
                )
            if subcommand == "report" and self.role != "copilot" and len(positional) > 1:
                if not any(
                    order["id"] == positional[1] for order, *_ in self.active
                ):
                    return f"{positional[1]} is not an order dispatched to {self.role}"
            if subcommand == "check" and len(positional) > 1:
                # Checks are shell commands from the spec. Agents may trigger
                # them only when the surgeon signed that exact spec; otherwise
                # an agent could author a check and run it past the guard.
                try:
                    if self.L is None:
                        raise StError("guard has no ledger")
                    order = self.L.order(positional[1])
                    ok, _ = verify(
                        order.get("approval"),
                        {
                            "kind": "approve",
                            "order": order["id"],
                            "spec_sha": sha(order["spec"]),
                        },
                    )
                except (StError, AttributeError):
                    ok = False
                if not ok:
                    return (
                        f"`st check {positional[1]}` needs a signed approval of the spec; under a "
                        "standing order the surgeon runs the checks"
                    )
            return None
        if name == "git":
            return self.check_git(args, current)
        inplace = any(
            re.match(r"^-[A-Za-z0-9]*i", arg) or arg.startswith("--in-place")
            for arg in args
        )
        if name in INPLACE_EDITORS and inplace:
            why = self.outward_arg(args, current)
            if why:
                return why
        if name in FILE_MUTATORS or (name in INPLACE_EDITORS and inplace):
            paths = [arg for arg in args if not arg.startswith("-")]
            if name in INPLACE_EDITORS:
                paths = paths[1:]  # first word is the script
            if not paths:
                return None if in_workspace else self.no_ws_msg(f"`{name}` in {current}")
            for path in paths:
                if UNRESOLVED.search(path):
                    return f"`{name}` argument {path!r} cannot be resolved by the guard"
                why = self.check_write_target(path, current, name)
                if why:
                    return why
            return None
        if name == "find" and any(
            arg
            in ("-delete", "-exec", "-execdir", "-ok", "-okdir", "-fprint", "-fprintf", "-fls")
            for arg in args
        ):
            if not in_workspace:
                return self.no_ws_msg(f"`find -delete/-exec` in {current}")
            return self.outward_arg(args, current)
        if name in INTERPRETERS and INTERPRETERS[name] in args:
            if not in_workspace:
                return self.no_ws_msg(f"inline `{name}` code in {current}")
            code = args[args.index(INTERPRETERS[name]) + 1 :][:1]
            return self.outward_arg(
                re.findall(r"""(?:~|\.\.|/)[^\s'"(),;]*""", code[0]) if code else [],
                current,
            )
        if name == "eval":
            return None if in_workspace else self.no_ws_msg(f"`eval` in {current}")
        if name in ("curl", "wget"):
            bad = {
                "-d",
                "--data",
                "--data-binary",
                "--data-raw",
                "--data-urlencode",
                "-F",
                "--form",
                "-T",
                "--upload-file",
                "--post-data",
                "--post-file",
            }
            if any(arg in bad or arg.split("=")[0] in bad for arg in args) or any(
                arg in ("-X", "--request") for arg in args
            ):
                return (
                    f"{name} with an upload or custom method is denied: "
                    "it can send project data out"
                )
            return None
        if name in ("scp", "sftp", "nc", "ncat", "socat"):
            return f"{name} is denied: outbound transfer"
        if (
            name in ("brew", "gem")
            or (name == "cargo" and args[:1] == ["install"])
            or (name == "go" and args[:1] in (["install"], ["get"]))
            or (
                name in ("npm", "pnpm", "yarn")
                and any(arg in ("-g", "--global") for arg in args)
            )
            or (name in ("pip", "pip3") and "--user" in args)
        ):
            return f"`{name} {' '.join(args[:1])}` changes global state, which is L3"
        package_mutators: dict[str, set[str]] = {
            "npm": {"install", "i", "add", "ci", "uninstall", "remove", "update"},
            "pnpm": {"install", "i", "add", "remove", "update"},
            "yarn": {"install", "add", "remove", "upgrade"},
            "cargo": {"add", "remove", "update"},
            "pip": {"install", "uninstall"},
            "pip3": {"install", "uninstall"},
            "uv": {"add", "remove", "pip", "sync"},
            "poetry": {"add", "remove", "install"},
        }
        if (
            name in package_mutators
            and args[:1]
            and args[0] in package_mutators[name]
        ):
            return (
                None
                if in_workspace
                else self.no_ws_msg(f"`{name} {args[0]}` in {current}")
            )
        if name in READONLY_PROGS:
            return None
        if in_workspace:
            return self.outward_arg(args, current)
        return self.no_ws_msg(
            f"`{name}` in {current} (outside a workspace only read-only viewers, git reads, "
            "and st run; builds and tests run in a workspace)"
        )

    def check_git(self, args: list[str], current: Path) -> str | None:
        git_cwd = current
        index = 0
        while index < len(args) and args[index].startswith("-"):
            arg = args[index]
            if arg == "-C" and index + 1 < len(args):
                git_cwd = self.resolve(args[index + 1], git_cwd)
                index += 2
                continue
            if arg.startswith(("--git-dir", "--work-tree")):
                return "git --git-dir/--work-tree is denied; use the order's workspace"
            if arg == "-c" and index + 1 < len(args):
                index += 2
                continue
            index += 1
        if index >= len(args):
            return None
        subcommand, rest = args[index], args[index + 1 :]
        entry = self.ws_for(git_cwd)
        if subcommand in GIT_READ:
            return None
        if subcommand == "branch":
            if any(
                arg
                in (
                    "-d",
                    "-D",
                    "--delete",
                    "-m",
                    "-M",
                    "--move",
                    "-f",
                    "--force",
                    "-c",
                    "-C",
                    "--copy",
                )
                for arg in rest
            ):
                return "deleting, moving, or forcing branches is L3"
            if [arg for arg in rest if not arg.startswith("-")] and not any(
                arg in ("-l", "--list", "-a", "-r", "--contains", "--merged")
                for arg in rest
            ):
                return "creating branches is done by `st dispatch`"
            return None
        if subcommand == "tag":
            return (
                None
                if not rest or rest[0] in ("-l", "--list")
                else "tagging is L3"
            )
        if subcommand == "remote":
            return (
                None
                if not rest or rest[0] in ("-v", "show", "get-url")
                else "changing remotes is L3"
            )
        if subcommand == "config":
            if any(arg in ("--global", "--system") for arg in rest):
                return "global git config is L3"
            return (
                None
                if any(arg.startswith(("--get", "--list", "-l")) for arg in rest)
                else "changing git config is outside every order"
            )
        if subcommand == "worktree":
            return (
                None
                if rest[:1] == ["list"]
                else "worktrees are managed by `st dispatch`"
            )
        if subcommand == "stash" and rest[:1] == ["list"]:
            return None
        if subcommand == "reset":
            if "--hard" in rest:
                return "git reset --hard is L3"
            return None if entry else self.no_ws_msg(f"git reset in {git_cwd}")
        if subcommand == "clean":
            return "git clean is L3"
        if subcommand == "reflog":
            return None if not rest or rest[0] == "show" else "rewriting the reflog is L3"
        if subcommand in GIT_ALWAYS_DENY:
            return f"git {subcommand} is L3 (it rewrites or integrates history)"
        if entry and subcommand not in GIT_READ:
            # Options that choose where git writes must be literal: `$D` has no
            # slash for outward_arg to inspect, but can expand to any path.
            for rest_index, arg in enumerate(rest):
                option, _, value = arg.partition("=")
                if option in GIT_DIR_OPTS:
                    value = (
                        value
                        if "=" in arg
                        else (
                            rest[rest_index + 1]
                            if rest_index + 1 < len(rest)
                            else ""
                        )
                    )
                    if UNRESOLVED.search(value):
                        return (
                            f"git {subcommand} {option} {value!r} cannot be resolved by the guard"
                        )
            why = self.outward_arg(rest, git_cwd)
            if why:
                return why
        if subcommand in GIT_WORKTREE_OPS:
            if subcommand in ("checkout", "switch") and any(
                arg in ("-b", "-B", "-c", "-C", "--orphan") for arg in rest
            ):
                return "creating branches is done by `st dispatch`"
            return None if entry else self.no_ws_msg(f"git {subcommand} in {git_cwd}")
        if subcommand in GIT_HISTORY_OPS:
            if not entry:
                return self.no_ws_msg(f"git {subcommand} in {git_cwd}")
            if entry[1] < 2:
                return f"git {subcommand} needs L2; {entry[0]['id']} is L{entry[1]}"
            return None
        if subcommand == "push":
            return self.check_push(rest, git_cwd, entry)
        return f"git {subcommand} is not on the guard's allowlist; report the need"

    def check_push(
        self, rest: list[str], git_cwd: Path, entry: ActiveOrder | None
    ) -> str | None:
        if not entry:
            return self.no_ws_msg(f"git push from {git_cwd}")
        order, level, push, _ = entry
        if level < 2 or not push:
            return (
                f"{order['id']} does not permit a push; commit locally and report the branch ready"
            )
        for arg in rest:
            if arg in (
                "-f",
                "--force",
                "--mirror",
                "--all",
                "--tags",
                "-d",
                "--delete",
                "--prune",
            ) or arg.startswith(("--force", "--mirror")):
                return f"git push {arg} is L3"
        positional = [arg for arg in rest if not arg.startswith("-")]
        # ws_for can return an active entry only when Guard loaded a ledger;
        # this cast preserves the prior fail-closed AttributeError if that invariant breaks.
        ledger = cast("Ledger", self.L)
        remotes = set(git(["remote"], ledger.root, check=False).split())
        branch = (
            order["dispatch"]["branch"]
            if order.get("dispatch")
            else f"st/{order['id']}"
        )
        expected = f"st/{order['id']}-"
        if positional:
            if positional[0] not in remotes:
                return (
                    f"push target {positional[0]!r} is not a configured remote; "
                    "other destinations are L3"
                )
            for ref in positional[1:]:
                if ref.startswith("+") or ":" in ref or not ref.startswith(expected):
                    return f"push may only send the order's own branch ({branch})"
        return None
