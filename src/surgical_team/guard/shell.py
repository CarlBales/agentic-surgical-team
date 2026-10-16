"""Shell tokenizing and the program tables the guard checks against."""
from __future__ import annotations

import re
import shlex
from collections.abc import Sequence

SHELL_OPS = {";", "&&", "||", "|", "&", "|&", "(", ")", "{", "}"}
WRITE_REDIRECTS = {">", ">>", ">|", "&>", "&>>", ">&"}
READ_REDIRECTS = {"<", "<<", "<<<", "<&"}
FILE_MUTATORS = {
    "rm",
    "rmdir",
    "mv",
    "cp",
    "mkdir",
    "touch",
    "tee",
    "ln",
    "chmod",
    "chown",
    "truncate",
    "install",
    "rsync",
    "unlink",
    "shred",
}
INPLACE_EDITORS = {"sed", "perl", "ruby"}
INTERPRETERS = {
    "python": "-c",
    "python3": "-c",
    "node": "-e",
    "perl": "-e",
    "ruby": "-e",
    "bash": "-c",
    "sh": "-c",
    "zsh": "-c",
    "osascript": "-e",
}

# Programs that may run anywhere, including at L0 outside any workspace.
# Everything else (builds, test runners, scripts, interpreters) runs only
# with the working directory inside an order's workspace: test runners
# write artifacts, so "read-only test run" is not a thing (F-14).
READONLY_PROGS = {
    "cat",
    "less",
    "head",
    "tail",
    "ls",
    "rg",
    "grep",
    "egrep",
    "fgrep",
    "wc",
    "jq",
    "stat",
    "file",
    "diff",
    "find",
    "pwd",
    "echo",
    "printf",
    "true",
    "false",
    "which",
    "type",
    "date",
    "tree",
    "du",
    "df",
    "uname",
    "whoami",
    "basename",
    "dirname",
    "realpath",
    "readlink",
    "sort",
    "uniq",
    "cut",
    "tr",
    "column",
    "nl",
    "fold",
    "comm",
    "cmp",
    "shasum",
    "sha256sum",
    "md5",
    "md5sum",
    "test",
    "[",
    "sleep",
    "sed",
    "fd",
    "bat",
    "hexdump",
    "xxd",
    "od",
    "strings",
    "man",
    "rustc",
    "cargo-metadata",
}
WRAPPERS = {"command", "env", "time", "nohup", "nice", "xargs", "exec", "builtin"}
SHELLS = {"sh", "bash", "zsh", "dash", "ksh"}
GUARDED_ENV = {
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_COMMON_DIR",
    "GIT_OBJECT_DIRECTORY",
    "GIT_CONFIG",
    "GIT_CONFIG_GLOBAL",
    "GIT_CONFIG_SYSTEM",
    "ST_CONFIG_DIR",
    "ST_NOW",
    "HOME",
}
UNRESOLVED = re.compile(r"[$`]")  # variable or command expansion the guard cannot evaluate
GIT_READ = {
    "status",
    "log",
    "diff",
    "show",
    "blame",
    "rev-parse",
    "ls-files",
    "grep",
    "describe",
    "shortlog",
    "cat-file",
    "ls-tree",
    "rev-list",
    "fetch",
    "merge-base",
    "name-rev",
    "for-each-ref",
    "show-ref",
    "help",
    "version",
}
GIT_WORKTREE_OPS = {"add", "restore", "rm", "mv", "apply", "stash", "checkout", "switch"}
GIT_DIR_OPTS = {
    "--directory",
    "--prefix",
    "--work-tree",
    "--git-dir",
    "-C",
    "--output",
    "--output-directory",
    "-o",
}
GIT_HISTORY_OPS = {"commit", "cherry-pick", "revert", "am", "notes"}
GIT_ALWAYS_DENY = {
    "rebase",
    "merge",
    "filter-branch",
    "filter-repo",
    "update-ref",
    "replace",
    "gc",
    "prune",
    "pull",
}


def strip_heredocs(cmd: str) -> str:
    output: list[str] = []
    pending: list[str] = []
    for line in cmd.split("\n"):
        if pending:
            if line.strip() == pending[0]:
                pending.pop(0)
            continue
        for match in re.finditer(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1", line):
            pending.append(match.group(2))
        output.append(re.sub(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1", "", line))
    return "\n".join(output)


# M-5: the guard parses shell to decide where writes land, so it accepts only
# the grammar it can model soundly - simple commands, pipelines, `;`/`&&`/`||`,
# literal redirects, and `cd` to a literal path - and denies the rest. These
# reserved words introduce control flow the guard will not track; a command
# that needs them belongs in a script run from the workspace.
SHELL_KEYWORDS = {
    "if", "then", "elif", "else", "fi", "for", "while", "until", "do", "done",
    "case", "esac", "select", "function", "in", "time", "coproc", "!", "[[", "]]",
}


def expandable_heredoc_bodies(cmd: str) -> str:
    """The bodies of heredocs whose delimiter is unquoted (so they expand).

    `cat <<EOF` expands `$(...)` in its body; `cat <<'EOF'` does not. The
    substitution scan runs over command text plus these bodies, so a
    substitution hidden in an expanding heredoc is still seen.
    """
    bodies: list[str] = []
    pending: list[tuple[str, bool]] = []
    for line in cmd.split("\n"):
        if pending:
            delimiter, expand = pending[0]
            if line.strip() == delimiter:
                pending.pop(0)
            elif expand:
                bodies.append(line)
            continue
        for match in re.finditer(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1", line):
            pending.append((match.group(2), match.group(1) == ""))
    return "\n".join(bodies)


def substitution_reason(cmd: str) -> str | None:
    """Name a command or process substitution in `cmd`, or None.

    Quote-aware: single quotes suppress everything, double quotes still allow
    `$(...)` and backticks. `$((...))` is arithmetic and `${...}` is a plain
    parameter, so neither is flagged (a `$(` nested inside `${...}` still is).
    """
    text = strip_heredocs(cmd) + "\n" + expandable_heredoc_bodies(cmd)
    i, n, quote = 0, len(text), None
    while i < n:
        c = text[i]
        if quote == "'":
            quote = None if c == "'" else quote
            i += 1
            continue
        if c == "\\":
            i += 2
            continue
        if quote == '"':
            if c == '"':
                quote = None
            elif c == "`":
                return "a backtick command substitution"
            elif c == "$" and text[i:i + 3] != "$((" and text[i:i + 2] == "$(":
                return "a $(...) command substitution"
            i += 1
            continue
        if c == "'":
            quote = "'"
        elif c == '"':
            quote = '"'
        elif c == "`":
            return "a backtick command substitution"
        elif c == "$" and text[i:i + 3] != "$((" and text[i:i + 2] == "$(":
            return "a $(...) command substitution"
        elif c in "<>" and text[i:i + 2] in ("<(", ">("):
            return "a process substitution"
        i += 1
    return None


def shell_segments(cmd: str) -> list[list[str]]:
    lexer = shlex.shlex(
        strip_heredocs(cmd).replace("\n", " ; "),
        posix=True,
        punctuation_chars=";&|()<>{}",
    )
    lexer.whitespace_split = True
    lexer.commenters = ""
    segments: list[list[str]] = []
    current: list[str] = []
    for token in lexer:
        if token in SHELL_OPS:
            if current:
                segments.append(current)
            current = []
        else:
            current.append(token)
    if current:
        segments.append(current)
    return segments


STDIN_PATHS = {"-", "/dev/stdin", "/dev/fd/0"}


def shell_inline(args: Sequence[str]) -> str | None:
    """The command string a shell runs with -c (also combined, as in -lc), or None."""
    for index, arg in enumerate(args):
        if arg == "--":
            return None
        if re.fullmatch(r"-[A-Za-z]*c[A-Za-z]*", arg):
            return args[index + 1] if index + 1 < len(args) else ""
        if arg in ("-o", "+o", "-O", "+O"):
            continue
        if not arg.startswith(("-", "+")) and (
            index == 0 or args[index - 1] not in ("-o", "+o", "-O", "+O")
        ):
            return None  # first operand is a script file
    return None


def shell_reads_stdin(args: Sequence[str]) -> bool:
    """A shell with no script operand, -s, or a stdin path reads commands from stdin."""
    operands = [
        arg
        for index, arg in enumerate(args)
        if not arg.startswith(("-", "+"))
        and (index == 0 or args[index - 1] not in ("-o", "+o", "-O", "+O"))
    ]
    if any(re.fullmatch(r"-[A-Za-z]*s[A-Za-z]*", arg) for arg in args):
        return True
    return not operands or operands[0] in STDIN_PATHS or operands[0].startswith("/dev/fd/")
