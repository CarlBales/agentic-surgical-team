"""Git subprocess helpers and path utilities.

Workspace contents are agent-controlled. In particular, a linked worktree's
``.git`` file must never choose metadata for a Git command run by ``st``: Git
configuration can execute hooks such as ``core.fsmonitor`` on the host.
"""
from __future__ import annotations

import os
import re
import stat
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from .model import StError

if TYPE_CHECKING:
    from .ledger import Ledger


def git(args: Sequence[str], cwd: str | Path, check: bool = True) -> str:
    """Run host Git without inherited ``GIT_*`` routing or executable hooks.

    The caller supplies the repository explicitly through ``cwd`` or command
    arguments. An inherited Git variable must not be able to substitute a
    repository, index, config, executable, or external helper.
    """
    env = {name: value for name, value in os.environ.items() if not name.startswith("GIT_")}
    result = subprocess.run(
        ["git", *args],
        check=False,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
    )
    if check and result.returncode:
        raise StError(f"git {' '.join(args)}: {result.stderr.strip()}")
    return result.stdout.strip()


def _tampered(workspace: Path, detail: str) -> StError:
    return StError(
        f"workspace git metadata was tampered with at {workspace}: {detail}; "
        "refusing to run git in it. Inspect the workspace by hand before retrying"
    )


def _metadata_line(path: Path, workspace: Path, label: str) -> str:
    """Read one plain Git administrative-file line, rejecting links and extras."""
    try:
        mode = path.lstat().st_mode
    except OSError as error:
        raise _tampered(workspace, f"cannot read {label} {path}: {error}") from error
    if not stat.S_ISREG(mode):
        raise _tampered(workspace, f"{label} {path} is not a regular file")
    try:
        text = path.read_text()
    except (OSError, UnicodeError) as error:
        raise _tampered(workspace, f"cannot read {label} {path}: {error}") from error
    line = text[:-1] if text.endswith("\n") else text
    if not line or "\n" in line or "\r" in line or "\0" in line:
        raise _tampered(workspace, f"{label} {path} is not exactly one line")
    return line


def _metadata_target(
    path: Path, workspace: Path, label: str, prefix: str = ""
) -> Path:
    line = _metadata_line(path, workspace, label)
    if prefix and not line.startswith(prefix):
        raise _tampered(workspace, f"{label} {path} does not start with {prefix!r}")
    value = line[len(prefix):]
    if not value:
        raise _tampered(workspace, f"{label} {path} has no path")
    target = Path(value)
    if not target.is_absolute():
        target = path.parent / target
    try:
        return target.resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise _tampered(workspace, f"{label} {path} points to {value!r}: {error}") from error


def _registered_worktree(root: Path, workspace: Path) -> None:
    """Require Git's main-checkout registry to name this exact worktree path."""
    try:
        output = git(["worktree", "list", "--porcelain"], root)
    except StError as error:
        raise _tampered(workspace, f"cannot verify the main worktree registry ({error})") \
            from error
    wanted = workspace.resolve()
    registered: list[Path] = []
    for line in output.splitlines():
        if not line.startswith("worktree "):
            continue
        try:
            registered.append(Path(line[len("worktree "):]).resolve(strict=True))
        except (OSError, RuntimeError):
            continue
    if registered.count(wanted) != 1:
        raise _tampered(workspace, "it is not uniquely registered by the main checkout")


def _administrative_gitdir(root: Path, workspace: Path) -> Path:
    """Find the registry entry whose Git-owned backlink names ``workspace``.

    ``git worktree list --porcelain`` establishes the registered worktree
    path, but does not expose its administrative directory name. Git's
    ``.git/worktrees/<name>/gitdir`` backlink provides that name without
    trusting the workspace's own ``.git`` file.
    """
    parent = root / ".git" / "worktrees"
    try:
        entries = list(parent.iterdir())
    except OSError as error:
        raise _tampered(workspace, f"cannot inspect {parent}: {error}") from error
    gitfile = (workspace / ".git").resolve(strict=False)
    matches: list[Path] = []
    for entry in entries:
        if entry.is_symlink() or not entry.is_dir():
            continue
        try:
            backlink = _metadata_target(entry / "gitdir", workspace, "worktree backlink")
        except StError:
            continue
        if backlink == gitfile:
            matches.append(entry.resolve())
    if len(matches) != 1:
        raise _tampered(
            workspace,
            "the main checkout has no unique .git/worktrees backlink for it",
        )
    return matches[0]


def _verified_worktree(root: Path, workspace: Path) -> Path:
    root = root.resolve()
    workspace = workspace.resolve()
    if workspace.is_symlink() or not workspace.is_dir():
        raise _tampered(workspace, "the worktree path is not a regular directory")
    _registered_worktree(root, workspace)
    expected = _administrative_gitdir(root, workspace)

    actual = _metadata_target(
        workspace / ".git", workspace, "workspace gitfile", "gitdir: "
    )
    if actual != expected:
        raise _tampered(
            workspace,
            f"its gitfile points to {actual}, expected {expected}",
        )

    common = _metadata_target(expected / "commondir", workspace, "commondir")
    expected_common = (root / ".git").resolve()
    if common != expected_common:
        raise _tampered(
            workspace,
            f"{expected}/commondir resolves to {common}, expected {expected_common}",
        )
    return expected


def verified_worktree(ledger: Ledger, workspace: Path) -> Path:
    """Return trusted linked-worktree metadata or refuse before running Git.

    Registration is queried with Git running in ``ledger.root``. The
    workspace gitfile must be a regular file (never a directory or symlink),
    point to the corresponding main-checkout administrative directory, and
    that directory's ``commondir`` must point back to the main checkout.
    """
    return _verified_worktree(ledger.root, workspace)


def worktree_git(
    args: Sequence[str], ledger: Ledger, workspace: Path, check: bool = True
) -> str:
    """Run Git for a verified worktree without ever consulting ``ws/.git``."""
    gitdir = verified_worktree(ledger, workspace)
    return git(
        [f"--git-dir={gitdir}", f"--work-tree={workspace.resolve()}", *args],
        ledger.root,
        check=check,
    )


def repo_root(cwd: str | Path) -> Path:
    """Main worktree root, even when called from a linked worktree.

    Discovery is a filesystem walk. For a linked worktree, plain metadata
    files are verified against Git's registry from the main checkout before
    any Git process starts; a planted workspace config is never consulted.
    """
    path = Path(cwd).expanduser().resolve()
    directory = path if path.is_dir() else path.parent
    for candidate in (directory, *directory.parents):
        entry = candidate / ".git"
        try:
            mode = entry.lstat().st_mode
        except OSError:
            continue
        if stat.S_ISDIR(mode):
            return candidate.resolve()
        if not stat.S_ISREG(mode):
            raise _tampered(candidate, f"{entry} is not a regular file or directory")
        administrative = _metadata_target(
            entry, candidate, "workspace gitfile", "gitdir: "
        )
        common = _metadata_target(
            administrative / "commondir", candidate, "commondir"
        )
        if common.name != ".git" or not common.is_dir():
            raise _tampered(
                candidate,
                f"commondir resolves outside a main .git directory: {common}",
            )
        root = common.parent.resolve()
        _verified_worktree(root, candidate)
        return root
    raise StError(f"{directory} is not inside a supported git checkout")


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def in_git_checkout(directory: Path) -> bool:
    """Whether `directory` or a parent has a `.git` entry: a filesystem walk
    that saves a git subprocess for the many paths outside any checkout."""
    for parent in (directory, *directory.parents):
        try:
            (parent / ".git").lstat()
            return True
        except OSError:
            continue
    return False


def existing_directory(
    candidate: object, base: str | Path | None = None
) -> Path | None:
    """Resolve a tool target to its nearest existing directory.

    Targets often name files or directories that do not exist yet. Callers
    that need repository context can safely start discovery from the nearest
    existing parent instead of handing an invalid cwd to git.
    """
    if not isinstance(candidate, str) or not candidate:
        return None
    try:
        path = Path(candidate).expanduser()
        if not path.is_absolute() and base is not None:
            path = Path(base).expanduser() / path
        path = path.resolve(strict=False)
        while not path.is_dir():
            parent = path.parent
            if parent == path:
                return None
            path = parent
        return path
    except (OSError, RuntimeError, ValueError):
        return None


def slugify(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return value[:40].rstrip("-") or "work"
