#!/usr/bin/env python3
"""Mutation testing for the guard: does every refusal have a test that needs it?

The original operators replace message-return refusals in guard/core.py,
guard/shellcheck.py, and tools.py with allows. Cursor adds two other refusal
shapes: ``(None, reason)`` role-resolution results and
``CursorHost.respond(reason)`` calls. Its session store also has comparisons
that are safety gates rather than message returns, so this harness mutates the
expiry, prompt-match, and ambiguity decisions toward allowing the call.

Each mutant runs the guard corpus, Cursor host tests, and ledger-tampering
suites. A mutant that passes them survives: the safety decision could be
removed without any test noticing. Genuinely equivalent survivors must be
listed in EQUIVALENT by file, qualified function, and exact source line, with
a rationale; stale entries fail the harness.

Slow (one suite run per mutant, in parallel). Run before a release or after
changing the guard, not on every commit:

    python3 tests/mutate_guard.py [-j N] [--file guard/core.py] [--limit N]
"""
from __future__ import annotations

import argparse
import ast
import os
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGETS = [
    "guard/core.py",
    "guard/shellcheck.py",
    "guard/cursor.py",
    "guard/sessions.py",
    "guard/hosts.py",
    "tools.py",
]
SUITES = [
    "test_guard_corpus_suite",
    "test_hosts",
    "test_guard_state",
    "test_leases",
    "test_sources",
]

# A survivor belongs here only when the mutation has no observable behavior
# change, not merely because coverage is missing. Keys deliberately include
# the exact line text so a source edit makes the exception stale and visible.
EQUIVALENT: dict[tuple[str, str, str], str] = {}


@dataclass(frozen=True)
class MutationSite:
    """One source replacement and its stable review identity."""

    rel: str
    function: str
    operator: str
    line: int
    col: int
    end_line: int
    end_col: int
    replacement: str
    source: str
    line_text: str

    @property
    def key(self) -> tuple[str, str, str]:
        return self.rel, self.function, self.line_text

    @property
    def label(self) -> str:
        return f"{self.rel}:{self.line} in {self.function}() [{self.operator}]"


def _source_slice(
    source: str, line: int, col: int, end_line: int, end_col: int
) -> str:
    lines = source.splitlines(keepends=True)
    if line == end_line:
        return lines[line - 1][col:end_col]
    return (
        lines[line - 1][col:]
        + "".join(lines[line:end_line - 1])
        + lines[end_line - 1][:end_col]
    )


def _function_for(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> ast.FunctionDef:
    current = node
    while current in parents:
        current = parents[current]
        if isinstance(current, ast.FunctionDef):
            return current
    raise ValueError(
        f"mutation candidate at line {getattr(node, 'lineno', '?')} "
        "is not in a function"
    )


def _qualname(fn: ast.FunctionDef, parents: dict[ast.AST, ast.AST]) -> str:
    parts = [fn.name]
    current: ast.AST = fn
    while current in parents:
        current = parents[current]
        if isinstance(current, (ast.ClassDef, ast.FunctionDef)):
            parts.append(current.name)
    return ".".join(reversed(parts))


def _site(  # noqa: PLR0913
    rel: str,
    source: str,
    parents: dict[ast.AST, ast.AST],
    node: ast.AST,
    replacement: str,
    operator: str,
    end_node: ast.AST = None,
) -> MutationSite:
    end = end_node or node
    fn = _function_for(node, parents)
    line = node.lineno
    col = node.col_offset
    end_line = end.end_lineno
    end_col = end.end_col_offset
    if end_line is None or end_col is None:
        raise ValueError(f"AST has no end position for {rel}:{line}")
    return MutationSite(
        rel=rel,
        function=_qualname(fn, parents),
        operator=operator,
        line=line,
        col=col,
        end_line=end_line,
        end_col=end_col,
        replacement=replacement,
        source=_source_slice(source, line, col, end_line, end_col),
        line_text=source.splitlines()[line - 1].strip(),
    )


def _string_expression(node: ast.AST) -> bool:
    return isinstance(node, (ast.JoinedStr, ast.BinOp)) or (
        isinstance(node, ast.Constant) and isinstance(node.value, str)
    )


def _is_none(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and node.value is None


def _is_cursor_response(call: ast.Call) -> bool:
    return (
        isinstance(call.func, ast.Attribute)
        and call.func.attr == "respond"
        and isinstance(call.func.value, ast.Name)
        and call.func.value.id == "CursorHost"
        and bool(call.args)
        and not _is_none(call.args[0])
    )


def _comparison_operator(
    rel: str, function: str, node: ast.Compare
) -> tuple[str, str] | None:
    """Return an allow-directed replacement for a Cursor safety comparison.

    These are structural patterns, narrowed by function, rather than line
    numbers. The unit tests pin their exact source forms so a rewritten gate
    cannot silently fall out of mutation coverage.
    """
    if rel == "guard/sessions.py" and function == "_pending_expired":
        if any(isinstance(op, ast.Gt) for op in node.ops):
            return "False", "expiry-gate"
    if rel == "guard/sessions.py" and function == "_prune_older_than":
        if any(isinstance(op, ast.Gt) for op in node.ops):
            return "False", "expiry-gate"
    if rel == "guard/sessions.py" and function == "claim":
        if any(isinstance(op, ast.In) for op in node.ops):
            # A transcript that does not contain the dispatch prompt now matches.
            return "True", "claim-gate"
        if any(isinstance(op, ast.NotEq) for op in node.ops):
            # Equal-specificity matches now proceed to the first dispatch.
            return "False", "claim-gate"
    return None


def refusal_sites(rel: str):
    """Yield every allow-directed mutation site in one guard source file."""
    path = ROOT / "src" / "surgical_team" / rel
    source = path.read_text()
    tree = ast.parse(source)
    parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
    sites: list[MutationSite] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Return) and node.value is not None:
            value = node.value
            first = (
                value.elts[0]
                if isinstance(value, ast.Tuple) and len(value.elts) == 2
                else value
            )
            # Preserve the original 63 refusal mutants exactly: a string-like
            # return, or the first member of a (reason, state) return, becomes None.
            if _string_expression(first):
                replacement = (
                    "None"
                    if first is value
                    else f"None, {ast.unparse(value.elts[1])}"
                )
                sites.append(
                    _site(rel, source, parents, first, replacement, "return-refusal", value)
                )
            # Cursor resolve_role returns (role, reason), the reverse of the
            # shell checker's tuple. Removing the reason must pass through, not
            # invent a role that would still invoke the core and obscure the gap.
            if (
                isinstance(value, ast.Tuple)
                and len(value.elts) == 2
                and _is_none(value.elts[0])
                and _string_expression(value.elts[1])
            ):
                sites.append(
                    _site(rel, source, parents, value, "None, None", "tuple-refusal")
                )

        if isinstance(node, ast.Call) and _is_cursor_response(node):
            sites.append(
                _site(
                    rel,
                    source,
                    parents,
                    node.args[0],
                    "None",
                    "cursor-response",
                )
            )

        if isinstance(node, ast.Compare):
            fn = _function_for(node, parents)
            function = _qualname(fn, parents)
            comparison = _comparison_operator(rel, function, node)
            if comparison is not None:
                replacement, operator = comparison
                sites.append(
                    _site(rel, source, parents, node, replacement, operator)
                )

        if isinstance(node, ast.If) and isinstance(node.test, ast.Name) and node.test.id == "why":
            fn = _function_for(node, parents)
            function = _qualname(fn, parents)
            if rel == "guard/hosts.py" and function in {
                "KiroHost.respond",
                "CursorHost.respond",
            }:
                # Host response encoding is itself a fail-closed gate: bypassing
                # the deny arm must be caught even if a new caller is added.
                sites.append(
                    _site(rel, source, parents, node.test, "False", "response-gate")
                )

    sites.sort(key=lambda site: (site.line, site.col, site.operator))
    yield from sites


def mutate(rel: str, site) -> Path:
    d = Path(tempfile.mkdtemp(prefix="st-mut-"))
    shutil.copytree(ROOT / "src", d / "src")
    shutil.copytree(ROOT / "bin", d / "bin")
    os.symlink(ROOT / "skills", d / "skills")
    if site is None:
        return d
    if site.rel != rel:
        raise ValueError(f"site for {site.rel} cannot mutate {rel}")
    f = d / "src" / "surgical_team" / rel
    lines = f.read_text().splitlines(keepends=True)
    head = "".join(lines[:site.line - 1]) + lines[site.line - 1][:site.col]
    tail = lines[site.end_line - 1][site.end_col:] + "".join(lines[site.end_line:])
    f.write_text(head + site.replacement + tail)
    return d


def run(rel, site) -> tuple[str, bool]:
    """Return (mutant name, killed); site None runs the unmutated copy."""
    d = mutate(rel, site)
    try:
        env = {**os.environ, "ST_SRC": str(d / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
        result = subprocess.run(
            [sys.executable, "-m", "unittest", "-f", *SUITES],
            cwd=ROOT / "tests",
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        name = site.label if site else "baseline"
        if site is None and result.returncode:
            sys.exit(
                "baseline copy fails the suites; fix that first:\n"
                + result.stderr[-2000:]
            )
        return name, result.returncode != 0
    finally:
        shutil.rmtree(d, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("-j", type=int, default=min(8, os.cpu_count() or 4))
    parser.add_argument("--file", action="append")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    run("", None)  # the harness must pass the unmutated copy, or kills mean nothing
    targets = args.file or TARGETS
    all_jobs = [(rel, site) for rel in targets for site in refusal_sites(rel)]
    jobs = all_jobs[:args.limit]
    with ThreadPoolExecutor(args.j) as pool:
        results = list(pool.map(lambda job: run(*job), jobs))

    unexpected = []
    equivalent = []
    obsolete = []
    outcomes = []
    for (rel, site), (name, killed) in zip(jobs, results):
        outcomes.append((rel, site, killed))
        if not killed and site.key in EQUIVALENT:
            equivalent.append((name, EQUIVALENT[site.key]))
        elif not killed:
            unexpected.append(name)

    discovered_keys = {site.key for _rel, site in all_jobs}
    for key in EQUIVALENT:
        if key[0] not in targets:
            continue
        matching = [killed for _rel, site, killed in outcomes if site.key == key]
        if key not in discovered_keys:
            obsolete.append((key, "no mutation site has this identity"))
        elif matching and all(matching):
            obsolete.append((key, "every matching mutant is now killed"))

    for name in unexpected:
        print(f"SURVIVED {name}")
    for name, reason in equivalent:
        print(f"EQUIVALENT {name}: {reason}")
    for key, reason in obsolete:
        print(f"STALE EQUIVALENT {key!r}: {reason}")

    for rel in targets:
        per_file = [killed for outcome_rel, _site, killed in outcomes if outcome_rel == rel]
        killed = sum(per_file)
        print(f"{rel}: {killed}/{len(per_file)} mutants killed")
    killed = sum(1 for _rel, _site, was_killed in outcomes if was_killed)
    print(f"{killed}/{len(outcomes)} mutants killed")
    return 1 if unexpected or obsolete else 0


if __name__ == "__main__":
    sys.exit(main())
