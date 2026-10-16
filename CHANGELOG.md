# Changelog

Versions follow the control plane (`st --version`). `st` ships as a checkout:
`bin/st`, `src/`, `skills/`, and `schema/` travel together. Build a release
tarball with `scripts/release.sh`.

## Unreleased — optional by default

The team is there only when you call it, and it leaves nothing behind that
the project depends on. **Upgrading:** re-run `st install --host cursor` to
get the `/st` command and the `beforeSubmitPrompt` hook entry.

### Security
- Guard ledger discovery now fails closed when safe filesystem root validation
  cannot resolve a checkout whose top level contains `.surgical-team/`, such
  as a project using a submodule-style or `--separate-git-dir` gitfile. A
  scrubbed `git rev-parse --show-toplevel` probe distinguishes that team
  context instead of silently skipping blind-path checks; inherited `GIT_*`
  routing remains removed, and normal/linked-worktree discovery is unchanged
  (L8).
- Team-agent namespace checks now strip surrounding whitespace and case-fold
  names before comparing the `st-` prefix. Variants such as `ST-tester` and
  ` st-tester` can no longer pass through a plain Cursor chat as ordinary
  agents; copilot launches send them through the same guarded role, briefing,
  and dispatch validation as canonical names (L7).
- `st prune` no longer treats an unsigned terminal order state as authority to
  remove a worktree or delete a branch. Accepted and rejected orders require a
  matching verified surgeon-signed verdict, cancelled orders require their
  signed cancellation to verify, and accepted branches must still be merged
  before deletion (L6).
- Briefings now render decision title, rule, and dissent only from a verified
  surgeon signature. Unverified or missing decisions appear by ID and status
  in a separate non-authoritative warning section with their content withheld;
  dispatch refuses an order that names either as binding, while verified
  revoked, superseded, and expired bindings retain their prior status display
  and dispatch behavior (M4).
- Source release archives now exclude the tracked internal `docs/backlog.md`
  through a committed `export-ignore` attribute, while retaining public release
  documentation such as `README.md` (L9).
- Cursor team sessions are now documented and reported as supported and
  verified on the Cursor Agent CLI only. The guides, installer, generated
  `/st` command, copilot prompt, doctor output, and guard warnings prohibit
  Cursor IDE team sessions until IDE tool calls are observed reaching the
  user-level hooks. Recorded CLI payloads expose no reliable CLI/IDE surface
  discriminator, so the guard itself is unchanged except for its guidance (M3).
- Every role now refuses recognized agent-host CLIs, including direct paths,
  modeled shell wrappers, known `npx`/`bunx`/`pnpm dlx`/`uvx` package names,
  and literal Python `os`/`subprocess` launches. This is defense in depth for
  well-behaved models; workspace programs remain a sandbox concern. On Cursor,
  a top-level chat rooted in an order workspace now persists a refused binding
  instead of becoming plain or copilot, even when workspace Git metadata is
  unreadable; plain chats rooted in the main checkout remain ordinary Cursor
  (H2).
- Agents cannot write a path component named `.git` anywhere in an order
  workspace, whether through a file tool, shell redirection, or a recognized
  file mutator; `.gitignore` and `.gitmodules` remain writable project files.
  As defense in depth against code run inside a workspace, every `st`-owned
  Git operation for a linked worktree validates its regular, non-symlink
  gitfile and the main checkout's worktree registry/backlinks, then runs Git
  from the main checkout with explicit `--git-dir` and `--work-tree`. Tampered
  metadata is refused for checks, verdict/cancel cleanup, and prune, and all
  inherited `GIT_*` variables are removed from `st`'s Git subprocesses (H1).

### Changed
- Cursor Agent CLI team sessions are opt-in per chat. A chat whose first message
  is `/st` (the command `st install --host cursor` now writes to
  `~/.cursor/commands/st.md`, carrying the copilot prompt and skills) binds
  as the copilot; where the host fires `beforeSubmitPrompt`, a `/st` prompt
  binds even earlier. Every other Agent CLI chat rooted in the main checkout is
  plain, ordinary Cursor: the guard stays out except that it cannot launch
  `st-<role>` agents, and its own subagents bind as plain. Top-level chats
  rooted in order workspaces are refused instead. `sessionStart` no longer
  injects anything. A top-level chat whose transcript is unreadable is
  refused rather than guessed. This replaces the 0.6.0 behavior, where every
  chat in a team project was the L0 copilot and the surgeon's own Cursor
  agent could not edit the project.
- Briefings list every design decision in force, marking the order's
  `inputs.decisions` as binding, so uniform design no longer depends on the
  copilot remembering to list one.
- The status board marks a report its own checks contradict: `DONE` with
  failing checks, or `BLOCKED`/`DECLINED` only when every acceptance criterion
  has an executable check and all pass. After a check run on a manual-only
  order, the board says `no executable checks` instead of `checks 0/0 pass`
  (L5).

### Added
- `st decide --dissent "…"` (repeatable) signs an overruled objection into
  the decision; briefings show it and the board counts it.
- A verdict or `st cancel` removes the order's worktree when it is clean
  (accepted L1 work is uncommitted, so a dirty worktree stays). `st prune
  [--dry-run] [--force] [--into BRANCH]` removes closed orders' leftover
  worktrees and deletes `st/*` branches of rejected or cancelled orders and of
  accepted orders already merged. `st uninstall [--host kiro|cursor]`
  removes the user-level agents, hooks, and `/st` command, leaving ledgers
  and other hooks alone. Both are surgeon-only. `st doctor` reports the
  footprint and checks the `/st` command.

### Tests
- Unit tests isolate the Cursor directory (`ST_CURSOR_DIR`) so installs never
  touch the real `~/.cursor`.

### Validation moves local

- `scripts/check` runs the gate CI used to run, and `scripts/check
  --install-hook` installs it as a pre-push hook in `.git/hooks` (read-only to
  agents; it refuses to run in a linked worktree). Each pushed commit is checked
  in a clean clone, never the working tree. Mutation testing covers the guard
  files a push changes, and live scenarios run once per installed host when a
  push changes what agents run (`ST_SKIP_SCENARIOS=1` skips them). `--full`
  adds coverage and full mutation; `--linux` runs the suite in a container.
- CI runs only for pull requests on github.com, or by hand elsewhere: Linux
  tests at 3.9 and 3.13, types, lint, skills, and coverage. macOS, latency,
  nightly mutation, and the scenarios job (which had no runners) are gone.
- `scripts/check push [ARGS]` runs the gate, live scenarios included, before git
  connects, then pushes. The first real push ran them inside the hook, and the remote
  closed the idle connection, so the push failed after the checks finished.
  Passing commits are stamped in `.git/st-check/`, so the hook accepts them at once.
  A plain `git push` that needs the scenarios is refused immediately, and the
  hosts' scenarios now run in parallel.
- The guard's control-plane refusal for a command run through a variable
  (`ST=…; $ST report …`) now says to call `st` by name or literal path and
  retry. It is still a refusal. In the live sweep a TypeScript lawyer gave up
  after the old message and filed no report.
- `scripts/publish` sends scanned snapshots to a public remote. `export-ignore`
  paths stay out. Every path, every line, and the message are checked against
  built-in rules (keys, tokens, home directories, personal email addresses,
  confidentiality markers) and a private, untracked denylist. Each snapshot is
  a single commit on the public tip under a public identity, gated, then
  pushed, so the internal history, authors, and deleted files never leave. The
  pre-push hook refuses any other commit on a public remote (`st.publicRemote`,
  or any github.com, gitlab.com, codeberg.org, or bitbucket.org URL), even
  with `ST_SKIP_CHECK=1`.
- `scripts/release.sh` honors `ST_DIST_DIR`; the release test builds in its own
  temp directory, so two suites in one tree no longer race on `dist/`.

## 0.6.0 — Cursor host

Cursor joins Kiro as a host (X-1). The guard core and the authority model
are unchanged; the guard corpus runs through both adapters.

**Upgrading:** re-run `st install` (Kiro) and/or `st install --host cursor`
after upgrading; `st doctor` flags out-of-date Cursor subagent files.

### Added
- `st install --host cursor`: one `~/.cursor/agents/st-<role>.md` subagent
  per specialist (protocol and role skill inlined), and `st guard --host
  cursor` on `sessionStart` and `preToolUse` merged into
  `~/.cursor/hooks.json` (`failClosed`; other hooks kept). `--dir` and
  `--hooks` override both destinations.
- The Cursor adapter translates Cursor's tool names and inputs to the
  normalized event. Cursor's `Task` is a subagent launch, never the todo
  tool that a bare `task` aliases to.
- Role binding for Cursor's global hook (`guard/sessions.py`, under the
  trust root): `sessionStart` in a ledger project makes the chat the
  copilot and injects its prompt, skills, and `st status`. An allowed
  copilot `Task` records a pending dispatch, and the subagent claims it,
  once, when its transcript opens with that exact prompt. An unbound
  conversation in a ledger project is refused; outside one, the guard
  stays out.
- `st doctor` reports each installed host, out-of-date Cursor subagent
  files, the Cursor hook entries, and the `cursor-agent` version.
- `tests/guard_corpus.py --host cursor|all`, `tests/scenarios.py --host
  cursor`, `scripts/sandbox --host cursor`, and a per-host CI scenarios
  matrix (self-hosted runners labelled `kiro` and `cursor`).

### Security
- `~/.cursor` (agents, hooks, transcripts) and `<project>/.cursor` are
  guard-protected control-plane state, on both hosts. For a bound team
  conversation, the one exception is a raw `Write` to that event's own
  `~/.cursor/projects/<slug>/agent-tools/<file>` path.
- `scripts/sandbox` no longer lets workspace code reach the host through the
  shared `.git/`: hooks, config (`core.fsmonitor`, filters), `HEAD`, `main`,
  and replace refs are read-only in the container, so nothing planted there
  runs at the surgeon's next `git` command or changes what the host checks
  out. A real-container test checks each escape (N1).

### Changed
- Guard mutation testing now includes Cursor role-resolution tuple refusals,
  permission responses, session expiry and dispatch-claim comparisons, and
  Kiro/Cursor deny-response gates. The mutant suites include `test_hosts` and
  the two-host corpus; the harness still verifies an unmutated baseline,
  requires source-keyed rationales for equivalent survivors, and reports
  killed/total per file (I1).
- Release tarball verification now runs a targeted black-box smoke against the
  extracted tree's own `bin/st`: ledger lifecycle and schema validation,
  skill-derived role discovery, and a fail-closed guard corpus case. Required
  archive contents and exclusion of `.venv` remain checked (I2).
- Documentation now describes the Kiro and Cursor host adapters, Cursor's
  global role-bound hook, and the sandbox's scoped protection accurately.
  Dated records retain their original context with correction notes, and the
  improvement review records I1, I2, I4, I5, and I6 as done (I6).
- A live local Cursor CLI re-check on versions 2026.10.01-e373342 and
  2026.10.14-0f9edde recorded parent `Task` and child tool payloads but no
  `subagentStart` or `subagentStop` event. A configured start denial never ran
  and did not stop the child, so the guard continues to use its fail-closed
  transcript claim rather than installing an unverified lifecycle binding
  (I3).
- `st doctor` reports Cursor's unguarded cloud agents as an informational
  row instead of a permanent warning, so a healthy Cursor install reads
  "all good" (N6).

### Fixed
- Cursor installation now refuses to rewrite `hooks.json` when any hook event
  is not a list, naming the malformed event and leaving the file untouched
  instead of silently dropping it. Valid event lists still preserve every
  non-team entry exactly, including opaque non-object entries (I4).
- Guard decisions now recover a single ledger from explicit tool targets when
  the event cwd is outside a team checkout, using nearest-existing-directory
  resolution shared with Cursor binding. Blind read/search checks and
  repository-local protected paths therefore remain enforced for operation and
  image paths, file/path fields, shell working directories, and path-like shell
  arguments. Calls spanning multiple team ledgers or conflicting with the cwd
  ledger fail closed; target discovery still grants authority only through the
  matching signed grant and live lease (D10).
- Cursor `SemanticSearch` now preserves every target directory for independent
  blind-path checks instead of reducing multi-target searches to the event cwd.
  Zero targets still use the cwd, and one target keeps its existing path shape
  (D9).
- Cursor session state is now bounded without adding per-tool directory scans:
  interactive team `sessionStart` removes pending and claimed dispatch records
  after one hour and session/binding records idle for 14 days. Binding use
  refreshes its activity time. A retained top-level session can restore only
  the copilot role after binding cleanup; a pruned specialist is refused
  rather than assigned another role (D8).
- Read-only source specs now accept Cursor's recorded raw MCP tool form,
  `MCP:<tool>`, in addition to Kiro's `@server/tool`. Grants still require
  `"readonly": true` and match the complete host-reported name exactly; no
  basename fallback crosses hosts or servers. Cursor's payload omits its
  configured server name, so same-named tools on two Cursor MCP servers remain
  indistinguishable and are documented as unsupported collisions (D7).
- Cursor's large-output spill exemption now runs only after role resolution
  and allows only raw `Write` calls beneath the current workspace-root
  project's `agent-tools/` directory. Unbound team conversations, another
  project's slug, and `Delete` remain denied (D6).
- Cursor now discovers a team ledger from a tool's file/search target or shell
  working directory as well as hook project context, walking nonexistent
  targets to an existing parent. Unbound calls targeting a team repository are
  refused. An unbound conversation with no ledger context still tries to claim
  a pending dispatch from its transcript; only one with no transcript yet is
  refused while a dispatch is pending (D5, N2).
- Cursor `sessionStart` events marked `is_background_agent` now stay unbound
  in team projects and receive a safety warning, so later tool calls are
  refused if hooks fire. The copilot prompt, `st doctor`, and safety docs now
  say never to use cloud/background agents: cloud agents do not load `st`'s
  user-level hooks, have early unhooked reads, and lack `sessionStart` (D4).
- Blind orders now deny directory content searches rooted above withheld paths
  even when Kiro `include` or Cursor `glob` filters are supplied. Filtered
  `grep`, code searches, and shell `rg -g`/`grep --include` are covered, while
  searches rooted in non-blind directories remain allowed (D3).
- Subagent launch prompts must carry exactly one live order's briefing for
  their role and must not embed another live order's briefing header, across
  Kiro and Cursor; a plain mention of another order (`scope.out`) is allowed.
  Cursor transcript binding selects the unique longest matching pending
  prompt and refuses distinct equal-length matches, so a briefing embedded in
  another Task prompt cannot cross-bind roles (D2, N4).
- `scripts/sandbox` now lets the team run in the network-disabled container:
  `.surgical-team/`, `.git/`, `leases/`, and `cursor/` are writable, while the
  main checkout's source, signer configuration, and, inside `.git/`, `config`,
  `hooks/`, `info/`, `HEAD`, `index`, `packed-refs`, `modules/`, and every ref
  except `refs/heads/st/` stay read-only. `--team-root` mounts a development
  checkout read-only with its `bin/` on `PATH`; `--no-tty` supports
  automation. Opt-in real Podman/Docker tests run an order's lifecycle and
  check the git escapes below (D1, N1).
- Re-launching the same briefing no longer locks the retry out for an hour:
  identical pending records are one candidate and the oldest is claimed (N3).
- A Cursor subagent whose first tool call arrives before its transcript is
  written (seen live under load) is no longer refused as unbound: while a
  dispatch is pending, the guard waits up to 5 s for the transcript before
  deciding the claim (N7).
- Guard latency is back to the 0.5.0 level. Ledger discovery for tool
  targets skips directories outside any git checkout without a subprocess
  and caches lookups per call; a shell call naming outside paths fell from
  163 ms to 89 ms (N5).

## 0.5.0 — control plane hardening

Guard, structure, types, schemas, CI. No change to the authority model or the
ledger's meaning; the on-disk format gained a version marker (format 1).

### Security
- Closed an `eval` guard bypass and its siblings: from a workspace,
  `eval "cd ../../proj; rm x"` and the like modified the main checkout (S-1).
- Narrowed the shell grammar the guard accepts to what it can model —
  simple commands, pipelines, `;`/`&&`/`||`, literal redirects, `cd` to a
  literal path — and deny the rest. This closed control-flow keywords
  (`for`/`if`/`while`/…) and command and process substitution hiding
  outward writes (M-5).
- The installed guard hook fails closed: any guard exit other than 0 or 2
  becomes a block, since the host otherwise allows the call (H-1).
  **Re-run `st install` after upgrading.**
- `ST_NOW` (the test clock) is honored only when `ST_CONFIG_DIR` is set, so
  a planted clock cannot shift approval expiry in a real install (M-8).

### Added
- `st doctor`: a read-only check of versions, key policy, trust root,
  installed role agents (missing and stale), ledger format, and guard
  latency (X-2).
- `st migrate`: upgrade the ledger's on-disk format; never edits specs, so
  approvals stay valid (M-3).
- JSON Schemas for every ledger record and the order spec, under `schema/`:
  the on-disk contract a port must honor (M-3).
- `st draft` rejects unknown spec fields instead of ignoring them (M-3).
- A host-adapter seam: the guard core takes a normalized tool event, and
  Kiro's hook format lives in one adapter. `st guard --host` (X-1).
- `scripts/sandbox`: run a session in a container with the mainline and the
  trust root read-only — the strong control the guard cannot impose (X-3).
- `scripts/release.sh`: source release tarball.

### Changed
- `bin/st` (2,090 lines) split into the stdlib package `src/surgical_team/`,
  a one-way module graph, each module under ~400 lines (M-1).
- Full static typing under `mypy --strict`; `ruff` and CI on Linux and
  macOS, Python 3.9–3.13; branch coverage ≥ 85%; a guard conformance corpus
  and guard mutation testing (M-2, M-4, M-6, M-7).
- Guard latency cut 3–4× and made independent of the number of live orders
  (read ~59 ms; P-1).
- Supported Python floor stated as 3.9, the version stock macOS ships (M-9).

## 0.4.0 — the specialist roster

- Added TypeScript, Python, and C# language lawyers; a React Native platform
  lawyer; general, security, infra, and accessibility reviewers; an
  archaeologist and an incident analyst; and an archivist.
- Roles are derived from skill frontmatter, not a hardcoded list (E-1).
- Orders can name a commit range to review, pinned to SHAs (E-4), and grant
  read-only external tools (E-3). A shared consultant contract (E-2).

## 0.3.0 — authority out of the repository

- Live authority comes from a signed, append-only lease store outside the
  repository, never from the ledger's state. Approvals expire and back one
  attempt. See `docs/findings.md`.

## 0.1.0 — specifications

- The surgical-team agent skills, before the deterministic control plane.
