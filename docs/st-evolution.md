# `st` evolution: review and backlog

Review date: 2026-10-12, at v0.4.0 (`bin/st` is 2,090 lines,
`tests/test_st.py` 992, `tests/scenarios.py` 274). Question: is Python the
right language for `st`, and how does it become maintainable?

## Verdict

**Keep Python for now. The language isn't the maintainability problem; the
single file, the missing types, and the absence of CI are. Rust is a
reasonable destination for one part of `st`, but a rewrite today would port
the current defects along with the code and slow down a design that's still
changing.**

Each point below was measured or read in this review:

1. **The design is still moving.** v0.1 to v0.4 took six days. Last week
   alone changed how roles are defined (E-1), what an order can name (E-4),
   and which tools the guard admits (E-3). A rewrite pins the semantics in
   the slower language at exactly the moment they're changing fastest. Port
   once the spec stops moving, not before.
2. **The guard's hard problems aren't language problems.** Its defects come
   from modeling shell semantics; memory safety and types don't come into
   it. During this review, `eval "cd ../../proj; rm README.md"`, run from
   inside a workspace, **modified the main checkout** (S-1). A Rust guard
   built on the same model would have the same hole. Neither standard
   library includes a shell parser.
3. **Python isn't the latency cost.** A guard call measured 125 ms median
   with five live orders, against a 20 ms bare interpreter start. Each call
   forks `ssh-keygen -Y verify` once per live lease (five forks here), and
   the in-process verify cache never hits, because every tool call starts a
   fresh guard process. A Rust port that still shells out to `ssh-keygen`
   would save roughly the interpreter start and nothing else.
4. **The tests are already language-neutral.** Every unit test drives
   `bin/st` as a subprocess. That's why the suite is slow (63 s for 78
   tests), and it's also what would make a later port safe: the same suite
   can check a Rust binary unchanged. Keep that property.
5. **Zero-install matters.** `st` is stdlib-only and runs on the stock
   macOS Python. 26 tests passed on `/usr/bin/python3` 3.9.6, even though
   the README asks for 3.10 or later. A Rust binary gives the same property
   through a different route (one static file). Neither option wins here.

Rust does win on two points, and they're the triggers for R-1:

- **Native signature verification.** Python's standard library can't verify
  Ed25519 SSH signatures without a dependency, so it forks `ssh-keygen`.
  Rust can verify SSHSIG in-process, which removes the per-lease forks from
  every guard call. This is the strongest technical argument for a
  compiled guard.
- **Fail-closed by construction.** Tool kinds, order states, and authority
  levels become enums the compiler forces you to handle exhaustively.
  Schemas can be strict (unknown fields rejected) at parse time. Today the
  guard fails closed by convention and by tests (audit A-1 was a
  fall-through to allow).

Two costs to weigh honestly. The engineers likely to inherit `st` read
Python and TypeScript more than Rust. And splitting `st` across two
languages would duplicate the authority logic, which is the most
security-critical code in it. Either port the core as a whole, or don't
port it.

## What the review found

| # | Finding | Evidence |
|---|---|---|
| R1 | Guard bypass: `eval` is allowed inside a workspace without inspecting its argument, while `sh -c` is recursed into | `bin/st` `check_program`: `if name == "eval": return None if in_ws`; live probe modified the main checkout |
| R2 | Single 2,090-line file, 109 functions, four classes; `Guard` alone is about 570 lines | `grep '^# ---' bin/st` |
| R3 | Partial typing: 48 of 109 functions declare a return type; no type checker configured | grep count; no `pyproject.toml`, `mypy.ini` |
| R4 | Records are untyped dicts validated by hand; no schema file; no ledger format version | `validate_spec`; no version field in orders |
| R5 | No CI; `ruff` with E, F, B, S, PL rules reports 226 findings (168 of them line length) | no `.github/`; `ruff check --statistics` |
| R6 | Guard latency grows with live leases (one `ssh-keygen` fork each). Under a standing order, `decision_status` also verifies every decision to look for revocations, which is O(D) more forks (read in code, not measured) | 125 ms median with 5 leases; subprocess spy: `ssh-keygen -Y` ×5 per call |
| R7 | `Guard.__init__` verifies every live lease, then filters by role | `live_orders(...)` then `if o["spec"]["role"] != role: continue` |
| R8 | Test seams in production: `ST_NOW` moves the clock for expiry checks; `ST_CONFIG_DIR` moves the trust root | `bin/st:73`, `:133`; mitigated by `GUARDED_ENV`, but honored if the surgeon's environment has them set |
| R9 | Tests: one 992-line file, all subprocess-driven, ssh key generated per test, no coverage measurement, no in-process tests of the parser | 63 s for 78 tests |
| R10 | Scenarios are single-run pass/fail and not run on any schedule | README "Limits" |
| R11 | POSIX-only (`fcntl`, POSIX paths, POSIX shell model); hook input was host-coupled at review time (now Kiro and Cursor adapters) | `import fcntl`; `src/surgical_team/guard/hosts.py` |
| R12 | Installed agent configs go stale silently when roles are added | v0.4 needed a manual `st install` |

**Update (2026-10-14, I6).** The hook-format portion of R11 is resolved;
the POSIX limitation remains. The X-3 backlog entry below is likewise a dated
proposal, not the shipped interface: `st dispatch --sandbox` did not ship.
`scripts/sandbox` wraps the whole host session and, after D1, protects the main
checkout's source and signer configuration while overlaying the ledger, Git
metadata, leases, and Cursor state read-write so the team can operate. That is
the scoped boundary described in the X-3 result, not a claim that all
control-plane state is immutable.

## Backlog

Priorities: P0 means fix now; P1 means before anyone else depends on `st`;
P2 means product hardening; P3 means a decision with explicit triggers.

### P0

**S-1 Close the `eval` bypass and audit its siblings.**
- Recurse into `eval` the same way `sh -c` is recursed into, or deny it.
- Then probe and pin, with regression tests: `source` and `.`; `command eval`, `builtin eval`, and `exec`; `trap`; alias and function definitions; zsh `=(…)` process substitution; `env -S`; `xargs sh -c`.
- Deny anything the guard can't model, in every workspace.
- Acceptance: each probe has a test, and the live probe leaves the main checkout clean.

### P1: maintainability, still in Python

**M-1 Package it.** Split into `st/` modules with a one-way dependency
order: `model` → `signing` → `ledger`, `leases` → `authority` →
`guard/shell`, `guard/tools` → `commands/*` → `cli`.
- `bin/st` becomes a thin launcher. The runtime stays stdlib-only.
- Distribute as a `zipapp`, so it's still one file on PATH.
- Acceptance: no module over about 400 lines, and the unit suite passes unchanged.

**M-2 Type it.**
- Dataclasses for `Spec`, `Report`, `Lease`, `Grant`, and `Signed`, parsed once at the boundary. No dicts flow past the parser.
- `mypy --strict` (or pyright strict) in CI.
- `Literal` and `Enum` for states, levels, statuses, and tool kinds, with `assert_never` on every dispatch over them.

**M-3 Schemas and a ledger format version.**
- JSON Schemas for order, report, lease, and each signed payload kind, under `schema/`. These become the contract any port must honor.
- Add `format` to every ledger record.
- Add `st migrate`, to replace ad hoc refusals like the v0.3 "pre-0.3 approval" check.

**M-4 Guard conformance corpus.** Move guard cases into
`tests/guard-cases/*.json`, each holding a ledger fixture, the role, the
event, and the expected allow or block with a reason substring.
- Start with the current `TestGuard`, `TestLeases`, `TestSources`, and the audit round-1 and round-2 bypasses.
- One runner executes the corpus against any `st` binary. This is the specification for R-1.

**M-5 Narrow the shell grammar the guard accepts.** Replace "known
dangerous programs are denied" with "known syntax is accepted, everything
else is denied."
- Write down the accepted grammar: simple commands, pipelines, `&&`, `||`, `;`, literal redirects, and `cd` to literal paths.
- Deny the rest outright: `eval`, `source`, functions, aliases, `trap`, substitutions, and anything the tokenizer flags as unusual.
- Accepting a parser dependency instead (a tree-sitter bash grammar, say) is the alternative. I'd take the narrower grammar first: it is smaller, auditable, and fails closed.

**M-6 Fast tests.**
- In-process unit tests for the pure functions (`shell_segments`, `validate_spec`, `aws_op`, authority computation), with an injected clock.
- One SSH key per test session instead of one per test.
- Split `test_st.py` by module. Keep the subprocess suite as the conformance layer.
- Branch coverage on `guard/`, plus periodic mutation testing of the guard. v0.3 did this by hand once, by reverting to state-based authority and confirming the tests failed.
- Target: unit layer under 15 s.

**M-7 CI.**
- `ruff` with a pinned config, the type check, and unit tests on the supported Python floor and current Python, on macOS and Linux.
- Scenarios on a manual and nightly trigger, three runs each, reporting pass rate rather than single pass/fail. (2026-10-15: they now run locally from the pre-push gate, `scripts/check`; CI had no runners with a Kiro or Cursor login.)

**M-8 Remove test seams from production.**
- Once tests run in-process, inject the clock instead of reading `ST_NOW`.
- The guard refuses to run with `ST_NOW` set, failing closed.
- Keep the `ST_CONFIG_DIR` override but document it.

**M-9 Decide the Python floor.** Either 3.9 (it works today on stock macOS)
or 3.10 as documented. Test the floor in CI and state it in `st doctor`.

**P-1 Guard latency.**
- Verify only the leases for the calling role (R7).
- Verify decisions lazily, and only for the standing order in use (R6).
- Skip authority computation for tool calls that don't need it.
- Budget: guard p50 under 50 ms with 10 live orders, measured by a benchmark in CI.
- Don't cache verifications on disk. A writable verification cache would let workspace code forge authority without a signature, which is strictly worse than the documented lease-store residual.

### P2: product

**X-1 Host adapters.** Separate the guard core (a normalized `ToolEvent`
in, allow or deny with a reason out) from host formats. Kiro first. Add
other hosts that have pre-tool hooks one adapter at a time, each with the
conformance corpus run through it.

**X-2 `st doctor`.** Checks:
- git and OpenSSH versions
- the key's signing policy
- `allowed_signers`
- installed agent configs against the current skills (R12), with stale or missing roles reported
- a guard latency sample

**X-3 OS sandbox option.** `st dispatch --sandbox` runs the specialist
under the platform sandbox, with the main checkout and
`~/.config/surgical-team` read-only. The docs already call this the strong
control. It's process orchestration, so the language barely matters, and it
does more for safety than a rewrite would.

**X-4 Releases.** Version tags, a changelog, and a `zipapp` artifact per
release. If R-1 happens, add signed binaries.

**X-5 Windows (explicitly deferred).** `fcntl`, path semantics, and a
PowerShell shell model add up to a separate guard. Don't start it without a
named user who needs it.

### P3: the Rust decision

**R-1 Port the core to Rust, behind triggers.** Re-decide when **two or
more** of these hold:

1. The ledger format (M-3) and the guard corpus (M-4) have gone two minor
   versions without a breaking change.
2. Guard latency after P-1 still exceeds budget in real sessions, and
   in-process signature verification is the remaining cost.
3. `st` is distributed beyond its author's machine, and Python version
   drift causes a real support issue.
4. A second maintainer who reads Rust exists.

If you port:
- Port the core, meaning signing, ledger, leases, authority, and guard, as one crate. Never port the guard alone, because two implementations of authority will drift.
- Keep the CLI surface byte-compatible.
- Pass the M-4 corpus and the black-box unit suite unchanged before switching the hook.
- Verify SSHSIG in-process, and validate it against `ssh-keygen -Y verify` on the same corpus, including `allowed_signers` options (namespaces, validity windows). Confirm the crate supports every option `st` relies on before committing.

**Alternative to keep on the table: Go.** It's also a single static
binary with fast startup, and easier for TypeScript and C# engineers to
read. It's weaker than Rust for fail-closed modeling, since it has no sum
types or exhaustive matching. Weigh it at the same decision point.

## Order

S-1, then M-4 (the corpus captures today's behavior before refactoring),
then M-1 and M-6, then M-2, M-3, M-7, and P-1, then the rest of P1, then P2.
Revisit R-1 at each minor release against its triggers.

## P-1 result (2026-10-12)

`tests/bench_guard.py`: one `st guard` process per call, 10 live orders plus
2 under a standing order, macOS, median of 25.

| Call | Before | After |
|---|---|---|
| read | 260 ms | 59 ms |
| write in workspace | 259 ms | 75 ms |
| shell in workspace | 281 ms | 86 ms |

Cost is now flat in the number of live orders (30 orders: same numbers).
Changes: only the calling role's leases are verified; a workspace path
verifies only the order it names; reads verify nothing unless a blind
order applies (blind lists only restrict, so they are read unverified);
revocations are screened by payload before their signature is checked;
`st guard` skips loading the CLI.

The 50 ms budget is **not met** for writes and shell. What remains is one
`ssh-keygen -Y verify` fork (about 8 ms), one `git rev-parse` (about 24 ms),
and interpreter start and imports (about 35 ms). The two ways to go
further were rejected:

- A cached or MAC'd verification result in the config directory. Workspace
  code that can read that directory could then mint a lease for any spec,
  not just reopen one the surgeon signed. That breaks the v0.3 invariant.
- Re-implementing git's repository discovery to avoid `rev-parse`:
  worktrees, gitfiles, `GIT_DIR`, and `safe.directory` make that a source
  of guard bugs for 24 ms.

In-process SSHSIG verification would remove the fork; that is R-1
trigger 2. The CI benchmark budget is set to 120 ms p50 to catch
regressions.

## X-3 result (2026-10-12)

`st` cannot sandbox the specialist itself: Kiro spawns subagents in-process
and the guard is only a pre-tool hook (allow/deny), so nothing `st` runs
wraps the agent's processes. A `dispatch --sandbox` flag would be theater.

Instead `scripts/sandbox` wraps the whole session in a container. It mounts
the project read-only with `.surgical-team/` and `.git/` overlaid read-write,
the sibling `<project>.st/` worktrees read-write, and the trust root read-only
with `leases/` and `cursor/` overlaid read-write; `--network none` remains in
force. Thus it protects main-checkout source, `allowed_signers`, and
`config.json`, but not ledger records, Git metadata, lease state, Cursor
bindings, or workspace contents. Since v0.3, tampering with that writable
state cannot grant more than an unexpired surgeon-signed spec. Verified both
by argv tests and by an opt-in real Podman/Docker test that drafts, dispatches,
writes in the worktree, and reports while a main-source write fails. A live
`kiro-cli` or Cursor model session still requires a user-built image with that
host CLI; `--team-root` can mount this checkout read-only and put its `bin/` on
`PATH`.

## Status (2026-10-12, v0.5.0)

Worked in priority order, one commit each, each verified before the next.

| Item | Commit | State |
|---|---|---|
| S-1 eval bypass + siblings | e30c6e8 | done |
| M-4 guard conformance corpus | de32506 | done |
| M-1 package split | 7ffa396 | done |
| M-6 fast tests, coverage, mutation | 02d0a88 | done |
| M-2 typing, mypy --strict | 68b4d56 | done |
| M-3 schemas, format version, st migrate | 0b07659 | done |
| M-7 CI | d6e9429 | done |
| P-1 guard latency | 06b81f4 | done (not to 50 ms; see above) |
| H-1 hook fails closed | d8dba17 | done (new finding, found during P-1) |
| M-5 narrow shell grammar | 1774065 | done |
| M-8 test seams | 8033e19 | done |
| M-9 Python floor (3.9) | 8033e19 | done |
| X-1 host adapters | c59a3fe | done |
| X-2 st doctor | 472cf03 | done |
| X-3 OS sandbox | 27ec240 | shipped as `scripts/sandbox`; `st` cannot sandbox itself |
| X-4 releases | d89f88a | done (source tarball, not a zipapp) |

Two findings surfaced while working and were fixed in place: **H-1** (a
broken guard hook failed open, because the host allows a tool call on any
hook exit but 2) and the **M-1 correction** that `st` ships as a checkout,
not a zipapp (the guard needs `skills/` beside the tool).

### X-5 — Windows: still deferred

No change. `fcntl` locking, POSIX path assumptions, and a different shell
model make the guard a separate implementation on Windows. Not started, and
not worth starting without a named user who needs it.

### R-1 — the Rust port: not now

Re-evaluated at 0.5.0 against the four triggers:

1. *Format and corpus stable for two minor versions* — **no.** Both the
   ledger format (M-3) and the corpus (M-4) were introduced in 0.5.0; zero
   minor versions have elapsed.
2. *Latency still over budget and in-process verification is the last cost*
   — **partly.** p50 is 59–86 ms, over the 50 ms aspiration, and the
   `ssh-keygen` fork is indeed what remains. But the latency is acceptable
   in practice and under the 120 ms CI budget, so this is not pressing.
3. *Distributed beyond its author, with Python drift causing real support
   pain* — **no.** No external distribution yet; it runs on 3.9–3.13.
4. *A second maintainer who reads Rust* — **no.**

Zero triggers firmly hold (one partially). **Decision: stay on Python.** The
work that would have de-risked a port is now done regardless — the black-box
suite and the guard corpus run against any `st` binary, so a future port has
an executable specification to pass. Revisit at the next minor release.
