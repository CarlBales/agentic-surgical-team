# Python Toolchain

The toolsmith installs and wires tools. The language lawyer reads their configuration, interprets diagnostics, and
recommends the smallest language-level fix. Every command here requires L1 because tools can import project code or write
caches, environments, generated metadata, and build artifacts.

## Establish the baseline
Read configuration before naming a diagnostic:

```text
pyproject.toml       project metadata, build backend, tool sections
.python-version      interpreter selection input; meaning depends on its tool
mypy.ini/.mypy.ini   mypy configuration
pyrightconfig.json   Pyright configuration
ruff.toml/.ruff.toml Ruff configuration
setup.cfg            legacy metadata and mypy/pytest or other tool sections
requirements*.txt    pip requirement inputs or exported lock material
uv.lock              uv lock state
poetry.lock           Poetry lock state
CI configuration     tested Python matrix and canonical commands
```

In the report, record exact versions from lockfiles, environment definitions, CI setup, or supplied command output. A
`pyproject.toml` tool section identifies configuration, not necessarily the executable version. If `requires-python`,
`.python-version`, and CI disagree, report the conflict before reviewing syntax.

At L1, prefer repository-defined commands. Useful discovery commands, only when within the order, include:

```bash
python --version
python -c 'import sys; print(sys.implementation.name); print(sys.version)'
ruff --version
mypy --version
pyright --version
pytest --version
python -m pip --version
uv --version
poetry --version
```

Do not run all of them by habit. Run only tools the project uses, inside its workspace and intended environment. Never
present installed global versions as the project's pins.

## Virtual environments and interpreter identity
A virtual environment isolates an interpreter's installed packages; it does not make dependency inputs reproducible by
itself. `python -m venv .venv` creates an environment using the invoking interpreter. Creating it is L1 and should be the
toolsmith's work unless the order explicitly asks for toolchain execution.

Use `python -m pip`, not an unqualified `pip`, when interpreter identity matters. The executable named `python` can still be
wrong for the project; compare it to the configured runner. Activation is shell convenience, not a correctness requirement.
CI often invokes the environment's executable directly.

**WRONG:** claiming compatibility with Python 3.9 after checking only under 3.12. **UNIDIOMATIC:** relying on an
already-active, undocumented environment. **TASTE:** `.venv` versus another conventional local environment directory when
the repository has no policy.

Do not inspect secrets in package-index configuration. Report redacted source names when relevant and hand credential
handling to the toolsmith or surgeon.

## Ruff linting and formatting
Ruff reads `pyproject.toml`, `ruff.toml`, or `.ruff.toml`. Establish the exact Ruff release, target Python version,
included/excluded paths, selected rules, extended selections, ignores, per-file ignores, preview setting, and formatter
configuration. Parent configuration and `extend` can alter the effective set.

The default lint selection is not "every rule." Never cite a rule merely because Ruff implements it; confirm it is selected
for the file. Representative real rules include:

| Code | Ruff name | Meaning |
|---|---|---|
| `F401` | `unused-import` | imported name is unused |
| `F821` | `undefined-name` | name is not defined |
| `E711` | `none-comparison` | comparison to `None` should use identity |
| `B006` | `mutable-argument-default` | mutable object used as an argument default |
| `S602` | `subprocess-popen-with-shell-equals-true` | subprocess call starts a shell |
| `A001` | `builtin-variable-shadowing` | variable shadows a Python built-in |

`B006` belongs to Ruff's flake8-bugbear-derived rules and `S602` to its flake8-bandit-derived rules. They require
corresponding selections such as `B` or `S`, or explicit codes. `S602` signals review; `shell=True` is not exploitable in
every constant-command use, while interpolated untrusted text is a semantic security defect. Explain the actual data flow
rather than treating severity as encoded by the lint.

Common L1 commands, when they match repository policy:

```bash
ruff check .
ruff format --check .
```

`ruff check --fix` and `ruff format` modify files. Do not run them on a review order or at L0. Even a documented automatic
fix can change semantics; Ruff marks some fixes unsafe. Review the diff after any permitted fix.

A `# noqa` should identify the narrow code where supported and explain a non-obvious reason. Adding a broad ignore to
silence generated code is **UNIDIOMATIC**; suppressing a genuine defect is **WRONG**. Verify exact rule names at
<https://docs.astral.sh/ruff/rules/> for the pinned Ruff version.

## mypy and Pyright
mypy and Pyright implement overlapping but not identical interpretations and extensions of the typing specification. Their
inference, import resolution, strictness switches, plugin systems, and diagnostics differ. State which checker produced the
result and its version.

Read mypy settings from `mypy.ini`, `.mypy.ini`, `pyproject.toml`, or `setup.cfg`, including per-module overrides, plugins,
ignored missing imports, and strictness. Read Pyright settings from `pyrightconfig.json` or the supported `pyproject.toml`
section, including execution environments, Python version and platform, include/exclude paths, stub path, and diagnostic
mode.

Typical L1 commands are:

```bash
mypy .
pyright
```

Use the repository's narrower target if defined. A clean run proves only that the selected checker accepted files in scope
under that configuration. It does not prove runtime type safety, another checker's acceptance, full import coverage, or
untyped function bodies.

Interpret diagnostics from the inside out:

1. Identify the expression and inferred type, not just the line.
2. Find where imprecision entered: an untyped dependency, `Any`, invariant
   mutable collection, overload choice, narrowing failure, or stale stub.
3. Check `.pyi`, plugin, and checker-version behavior before changing runtime
   code.
4. Fix the contract or implementation. Do not cast, add `Any`, or ignore unless
   the code establishes the fact the checker cannot express.

A narrow `cast` changes only static belief; it performs no runtime check. Using it to assert an unverified external value is
**WRONG**. A local cast after a validation the checker cannot follow can be **TASTE**, with a comment.

Keep `.pyi` and `.py` synchronized. For library surfaces, a stub check or a consumer-style type test may be needed; use the
project's established tool rather than inventing one. Checker diagnostics are versioned tool behavior, so cite the release's
docs and exact diagnostic text.

## pytest and test diagnostics
Test strategy belongs to the tester. The language lawyer may interpret fixture, collection, import, assertion, async, and
exception behavior in existing tests. Read pytest options in `pyproject.toml`, `pytest.ini`, `tox.ini`, or `setup.cfg` as
present, plus installed plugins and their versions.

Common L1 forms are:

```bash
pytest
pytest -q path/to/test_file.py
pytest -q path/to/test_file.py::test_name
```

Use only a node ID shown by collection or present in the file; do not invent one. Pytest writes `.pytest_cache` by default
and can import arbitrary project and plugin code, so it is never an L0 viewer.

Distinguish collection errors from test failures and teardown errors. Fixture scope changes lifetime and sharing; widening
it to speed a suite can introduce state leakage. `pytest.raises` should cover only the operation expected to fail, or an
earlier line can satisfy it accidentally. Exact message matching is brittle unless message text is the contract.

A passing test is evidence for the exercised case, not proof of general Python semantics. Do not claim a test proves thread
safety, cancellation safety, or all supported versions unless it actually exercises them.

## Builds and package metadata
`[build-system]` declares the build backend and requirements used to create sdists and wheels. `[project]` carries
standardized core metadata when the backend supports it; tool-specific sections do not automatically replace that contract.
Dynamic fields must identify how the backend supplies them.

A common frontend command is:

```bash
python -m build
```

It requires the `build` package and invokes the declared backend, usually in an isolated environment. Do not recommend it as
if it were in the standard library. Use the repository's uv or Poetry build command when that is the established frontend,
after verifying syntax in that tool's pinned documentation. Build and metadata inspection are L1 because backends execute
code and write `dist/` and other artifacts.

Review both wheel and sdist contents when distribution correctness is in scope. A source checkout passing tests does not
show that package data, stubs, entry points, or version files reached the built artifact. Publishing is L3; never run upload
or publish commands. State what artifact the surgeon should inspect and what established command they would run.

## pip, uv, and Poetry
These tools overlap but are not interchangeable.

- **pip** installs distributions from requirement specifiers and requirement
  files. A requirements file is not inherently a lock: reproducibility depends
  on exact transitive pins, hashes where policy requires them, indexes, platform
  markers, and the generation process.
- **uv** can manage environments, resolve projects, lock dependencies in
  `uv.lock`, and run commands. Treat that lock as uv-owned and use the project's
  documented uv workflow.
- **Poetry** owns dependency declarations and `poetry.lock` for Poetry-managed
  projects. Major-version command and metadata behavior can differ; consult the
  pinned version's documentation.

**WRONG:** edit a direct requirement but leave the authoritative lock inconsistent while claiming a reproducible update.
**UNIDIOMATIC:** alternate pip, uv, and Poetry ad hoc in one workflow. **TASTE:** which one a new project should choose;
that is a surgeon decision informed by the toolsmith.

Do not hand-edit a generated lock unless its tool documents that workflow. Do not regenerate a lock at L0. A lock update can
change unrelated transitive versions; inspect the full diff and explain every unexpected movement.

## Dependency judgment
For each proposed package ask:

1. Does the standard library at the supported minimum already meet the need?
2. Is the exact project and distribution name correct, avoiding a plausible
   typosquat?
3. Does its `Requires-Python` and platform-wheel coverage match the matrix?
4. What direct and transitive packages, native extensions, licenses, and build
   requirements enter the trust path?
5. Is maintenance established by surgeon-supplied evidence or an explicitly
   authorized read-only source? Never infer it from memory.
6. Is the package exposed in public types, exceptions, or serialized data?
7. Does the chosen constraint express compatibility intent rather than merely
   copying the newest observed release?

A package index listing is not proof of safety. Vulnerability claims require an authoritative advisory and an exact
affected-version comparison. Installing a package to inspect it is a mutation and potential code-execution event, not L0.

## Reading tracebacks
Read a traceback as a chain, not just its final line:

1. Identify explicit cause (`direct cause`) or implicit context (`during
   handling`). The later exception can be a translation, not the root defect.
2. Start at the exception type and message, then find the deepest relevant
   project frame. Skip framework internals only after understanding the boundary.
3. Follow local values from supplied logs or reproduction evidence; never invent
   values omitted from the traceback.
4. For `SyntaxError`, use the filename, line, offset, and text; the parser may
   point just after the missing token.
5. For an `ExceptionGroup`, preserve the tree of subexceptions and their
   individual tracebacks. Do not flatten it into the last leaf.
6. Separate primary failure from cleanup failure. A bad `__exit__`, `finally`,
   or fixture teardown can mask the original exception.

At L0, propose the smallest reproduction and label it unrun. At L1, capture the exact command, environment baseline,
complete exception chain, and exit status. A confident reconstructed traceback is still not execution evidence.

## Tool authority
Authoritative behavior comes from each pinned release's documentation:

- Ruff: <https://docs.astral.sh/ruff/>
- mypy: <https://mypy.readthedocs.io/>
- Pyright: <https://github.com/microsoft/pyright/tree/main/docs>
- pytest: <https://docs.pytest.org/>
- Python packaging specifications: <https://packaging.python.org/en/latest/specifications/>
- pip: <https://pip.pypa.io/en/stable/>
- uv: <https://docs.astral.sh/uv/>
- Poetry: <https://python-poetry.org/docs/>

Never invent a command option, config key, rule code, checker diagnostic, or lockfile guarantee. If documentation for the
pinned version is unavailable, write `Unverified` and state what versioned source or L1 run would settle it.
