# Findings log — adversarial review of v0.1

Review date: 2026-10-06. Scope: every file in the repository at commit
`79c0b61`. Lens: current practice in agentic workflow design and
orchestration (tool scoping, deterministic control planes, independent
verification, failure semantics, evaluation).

Findings are worked in priority order. A finding is closed only when the
change is in the repository and its verification is recorded below it.

| ID | Pri | Finding | Status |
|---|---|---|---|
| F-01 | P1 | Authority levels are enforced only by prompt | resolved |
| F-02 | P1 | Authority grants can be forged by writing a ledger file | resolved |
| F-03 | P1 | Deterministic duties (IDs, state, validation) are given to LLM roles | resolved |
| F-04 | P1 | The topology cannot run on the host: subagents cannot dispatch subagents | resolved |
| F-05 | P2 | Verification is self-attested; acceptance criteria are not executed independently | resolved |
| F-06 | P2 | Worktrees nest inside the repo; the ledger is invisible from them | resolved |
| F-07 | P2 | No failure semantics: no transitions, recovery, revision, or dependencies | resolved |
| F-08 | P2 | Budgets cannot be enforced by the agents they constrain | mitigated |
| F-09 | P2 | No behavioral evaluation of the roles | resolved |
| F-10 | P2 | Skill bleed: all roles load into one agent and trigger outside the team | resolved |
| F-11 | P3 | The surgeon is the throughput bottleneck; approval fatigue is designed in | mitigated |
| F-12 | P3 | Context is lost at every hop; the copilot is told it knows code it has not read | mitigated |
| F-13 | P3 | Tester and copilot are not independent of the work they judge | mitigated |
| F-14 | P3 | L0 "read-only" test runs are ill-defined | resolved |

---

## F-01 — Authority levels are enforced only by prompt

L0–L3 are the safety model, but every role runs with the same tools. An L0
agent is asked, not prevented, from writing.
Evidence: `skills/surgical-team-protocol/references/authority-levels.md`; no
agent configs exist; README lists per-role configs as an open question.

Host facts (Kiro CLI docs): a subagent stage's `role` is an agent config
name; each config has its own `tools`, `toolsSettings`, and hooks; a
`preToolUse` hook that exits 2 blocks the call. `write.allowedPaths` only
auto-approves, it does not restrict. Session-wide trust-all is inherited by
subagents.

Fix direction: per-role agent configs with minimal tool sets, plus a
`preToolUse` guard that checks every write and shell call against the
order's authority and workspace. Document what hooks cannot stop (shell
indirection) and the stronger option (OS sandbox or container).

**Resolution.** `st install` writes one Kiro agent config per role
(`st-copilot`, `st-tester`, …), each loading only the protocol and its own
skill, with a `preToolUse` hook (`matcher: *`) running `st guard --role R`.
The guard computes authority from signed ledger records on every call and
exits 2 to block. It confines writes to the order's workspace, allows only
viewers, git reads, and `st` outside one, blocks L3 git forms, global
installs, outbound uploads, privilege escalation, key access, and anything
it cannot resolve. Residual risk (code run inside a workspace is not
parsed) is documented in `authority-levels.md`, with the container
recommendation.
Evidence: `TestGuard` (22 tests); live smoke with `kiro-cli --agent st-tester
--trust-all-tools`: write to main checkout BLOCKED, `git commit` at L1
BLOCKED, write in workspace allowed; scenarios `tester_stays_in_workspace`,
`lawyer_L0_writes_nothing` PASS. Self-audit found 11 bypasses in the first
guard (`dd of=`, `tar -C`, `GIT_DIR=`, `pushd`, `xargs rm`, `sh -c`,
`python3 st approve`, `find -delete`, `cd $VAR`, code `pattern_rewrite`,
`export GIT_WORK_TREE`); all fixed and pinned by
`test_audit_bypasses_from_inside_a_workspace` and
`test_code_rewrite_is_a_write`.

## F-02 — Authority grants can be forged by writing a ledger file

Standing orders and approvals are markdown files in `.surgical-team/`, and
agents treat `DEC-` records as binding. Only the clerk is supposed to write
them, but that is also only a prompt. An agent, injected content, or a PR
contributor can plant a grant.
Evidence: `authority-levels.md` "Standing orders"; protocol "The ledger".

Fix direction: grants are honored only with provenance an agent cannot
produce — a signature from a surgeon-held key, created by a command the
guard refuses to run on an agent's behalf.

**Resolution.** Approvals, verdicts, cancellations, decisions, standing
orders, and revocations are signed with `ssh-keygen -Y sign` and verified
against `allowed_signers` in `~/.config/surgical-team/`, outside every
project and guard-protected. Approval binds the SHA-256 of the exact spec.
Surgeon commands are guard-blocked for every agent, and `st setup` refuses
a key that signs without a passphrase, touch, or confirmation (closing the
path where workspace code could sign).
Evidence: `TestSigning` (forged approval, spec edited after approval,
planted standing order, unknown key, revoked/expired, L3 refused);
`test_setup_refuses_unencrypted_key`; scenario `copilot_cannot_self_approve`
PASS.

## F-03 — Deterministic duties are given to LLM roles

The program clerk assigns monotonic IDs, tracks state, and renders
`STATUS.md`. The administrator validates order fields, creates worktrees,
and accounts budgets. These are functions; as LLM roles they are
nondeterministic (parallel orders can collide on an ID), slow, and can
corrupt the only durable memory.
Evidence: `skills/program-clerk/SKILL.md`, `skills/administrator/SKILL.md`.

Fix direction: a ledger CLI with schema-validated records, atomic IDs, and
an explicit state machine. Keep LLM judgment only where judgment is needed.

**Resolution.** `bin/st` replaces the administrator and program clerk:
JSON records validated on entry, IDs assigned under an exclusive file lock,
an explicit transition table, generated `STATUS.md`, `events.jsonl` audit
log. `skills/administrator` and `skills/program-clerk` removed.
Evidence: `test_parallel_drafts_never_collide` (8 concurrent drafts, 8
unique IDs), `test_rejects_malformed_orders`, `test_full_lifecycle_and_verdict`.

## F-04 — The topology cannot run on the host

Kiro subagents cannot spawn subagents ("The crew tool is only available to
the parent agent"). The architecture has the administrator dispatching
specialists, and every specialist asking the clerk to file. Neither is
possible when those roles are themselves subagents. Only the primary
session (the copilot) can dispatch.
Evidence: README architecture diagram; Kiro `subagent` tool docs.

Fix direction: the copilot is the only dispatcher; dispatch mechanics move
into the ledger CLI. Specialists return reports to the copilot, which files
them through the CLI.

**Resolution.** The copilot is the only dispatcher (`st dispatch` +
one subagent stage per order). The guard blocks `subagent` for every other
role, and for the copilot it requires each stage to use a guarded `st-<role>`
agent and carry exactly one order dispatched to that role.
Evidence: `test_only_copilot_dispatches_subagents`,
`test_subagent_stages_must_be_guarded_and_dispatched`; live: st-copilot
stage on `kiro_default` BLOCKED.

## F-05 — Verification is self-attested

Reports require evidence, but the agent being judged pastes it. Acceptance
criteria are written to be "checkable by a command" yet nothing runs them
independently. The copilot drafts the order and then judges the report.
Evidence: protocol "Reports"; `assets/report.md`.

Fix direction: acceptance criteria carry an executable `check` where
possible; the CLI runs them in the order's workspace and records the result
in the ledger independent of the agent's claim.

**Resolution.** Acceptance criteria carry an optional `check` command.
`st check` runs them in the workspace and records exit code, output tail,
HEAD, and dirty state per attempt, separate from the report. The board shows
`checks n/m pass` or `checks NOT RUN`; `st accept` warns on unrun or failed
checks; `st draft` warns when no criterion is executable. Agents may trigger
checks only on surgeon-signed specs, so an agent cannot author and run one.
Evidence: `TestChecks`, `test_agent_cannot_run_checks_it_authored`; live
`st check` PASS on the smoke order.

## F-06 — Worktrees nest inside the repo; ledger invisible from them

`git worktree add .surgical-team/scratch/<WO>` nests a full checkout inside
the surgeon's tree (duplicate sources for ripgrep, cargo workspaces, IDE
indexers, test discovery). The ledger is committed only by the surgeon, so
from inside a worktree `.surgical-team/` is absent or stale, and the
cold-start procedure fails.
Evidence: `skills/administrator/SKILL.md` "Workspaces"; protocol "Cold start".

Fix direction: worktrees outside the repo (`../<repo>.st/<WO-ID>`); the
ledger located by an absolute path the CLI resolves from any worktree.

**Resolution.** Worktrees at `../<repo>.st/<WO-ID>` on branch
`st/<WO-ID>-<slug>`; `st` resolves the main checkout via
`git rev-parse --git-common-dir` from any worktree.
Evidence: `test_worktree_is_outside_the_repo`,
`test_st_finds_main_ledger_from_worktree`.

## F-07 — No failure semantics

States are listed without transitions or owners. Undefined: agent crash
mid-order (stuck in `dispatched`), retry, revising an order after
`BLOCKED`, dependencies between orders, idempotent re-dispatch. "Exactly
one report per order" conflicts with re-dispatch after an unblock.
Evidence: `references/ledger-layout.md` "State" line.

Fix direction: an explicit state machine in the CLI, with attempts, a
`revise` transition, `depends_on`, and a stale-dispatch check.

**Resolution.** Transition table in `st`; per-attempt reports, checks,
verdicts; `revise` (voids approval), `reclaim`, `cancel`, `depends_on`
gating, `paths` overlap refusal, `STALE` flag at 2x budget.
Evidence: `test_blocked_then_revise_then_redispatch_is_attempt_2`,
`test_reclaim_stuck_order`, `test_stale_dispatch_is_flagged`,
`test_dependencies_gate_dispatch`, `test_path_overlap_serializes`.

## F-08 — Budgets cannot be enforced by the agents they constrain

"At 80% of budget, instruct the agent to report PARTIAL" assumes a
concurrent supervisor with an interrupt channel. In blocking subagent mode
there is none, and agents cannot meter their own tokens. The host's
subagent turn limit is not configurable.
Evidence: `skills/administrator/SKILL.md` "Budget enforcement".

Fix direction: treat budget as a scoping estimate, record actual wall clock
from dispatch/report timestamps in the CLI, and state plainly that hard
ceilings come from the host.

**Mitigated, not solvable inside the team.** Budgets are documented as
scoping estimates and standing-order ceilings; `st` records actual wall
clock from dispatch to report and flags `OVER BUDGET` and `STALE`. Hard
limits remain the host's (subagent turn limit, not configurable).
Evidence: protocol "Budgets"; `test_stale_dispatch_is_flagged`;
`test_standing_order_dispatches_within_limits` (budget ceiling).

## F-09 — No behavioral evaluation

`validate-skills.sh` checks frontmatter and links only. Nothing tests that
an L0 agent stays read-only, that the tester declines without a spec, or
that IDs never collide.

Fix direction: unit tests for the CLI and guard (deterministic), and a
scenario suite for role behavior runnable headless.

**Resolution.** `tests/test_st.py`: 51 deterministic tests.
`tests/scenarios.py`: 5 live headless scenarios asserting on ledger and
filesystem state, never on model output. First run 2/5; fixes to the blind
guard (listings over-blocked) and to the "stop at first block" instruction
brought it to 5/5, and 5/5 again after the guard hardening. Single-run
pass/fail; README says to rerun before trusting a prompt change.

## F-10 — Skill bleed

The README's recommended setup loads every role's skill into one agent.
Role descriptions ("Use when writing or reviewing tests") also trigger in
ordinary sessions, imposing protocol behavior (DECLINED, work orders) where
no team exists.
Evidence: README "Using it"; each skill's `description`.

Fix direction: each role agent loads only the protocol and its own skill;
descriptions gated on the surgical-team context.

**Resolution.** Each `st-<role>` agent loads only the protocol and its
own skill. Every description now says "load only in a surgical team
session", and the README warns against loading the skills into a general
agent. Evidence: `test_install_writes_valid_guarded_configs`;
`scripts/validate-skills.sh` OK.

## F-11 — The surgeon is the bottleneck

Every order needs approval, every report a verdict, every push a per-order
grant, and no standing order ships. The design itself names the unverdicted
report as its most common failure. The predictable response is
rubber-stamping, which SURGEON.md warns against.

Fix direction: risk-tiered defaults (L0 auto-dispatch), batched verdicts,
and a shipped, signed default standing order the surgeon can revoke.

**Mitigated.** `st init --default-standing` ships a signed standing
order for L0 work; `st grant` for routine L1; batch `st accept A B C`; the
board puts check results next to each verdict; SURGEON.md has a throughput
section saying where per-order attention pays (L2, pushes). Evidence:
`test_default_standing_order_covers_L0_only`, `test_batch_verdicts`. Whether
this prevents rubber-stamping in practice is not measured.

## F-12 — Context lost at every hop

Surgeon → copilot → order → specialist → report → copilot is a chain of
lossy summaries, and the administrator is told to pass "nothing else." The
copilot is told it "knows all the code intimately" and can answer "without
a survey," which an LLM that rebuilds state each session cannot do and
which contradicts "read before claiming."
Evidence: `skills/copilot/SKILL.md` "What you are for"; administrator
"Assemble the briefing".

**Mitigated.** The copilot skill drops "knows all the code" and
"without a survey" for "read the call sites before answering, and say which
you read". The briefing inlines the active decisions an order cites, and the
copilot passes the briefing verbatim plus conversational intent. The chain
of hops remains inherent to delegation; it is shorter now (no administrator
or clerk hop).

## F-13 — Judges are not independent

The tester is the same model, often with the implementation in context, so
"test from the spec" is aspiration. The copilot grades reports against
orders it drafted.

**Mitigated.** Blind orders (`spec.blind`): the guard blocks reading
and content-searching withheld paths for that role, so tests come from the
spec. The copilot skill says it is not an independent judge of orders it
drafted and recommends a clean-context second opinion; `st check` provides
an independent mechanical record. Same-model bias remains.
Evidence: `test_blind_order_withholds_implementation`; scenario
`blind_tester_finds_spec_violation` PASS (found the missing `ValueError`
without reading `clamp.py`).

## F-14 — L0 test runs are ill-defined

L0 permits "test runs that do not write to the repo," but most test runners
write build artifacts (`target/`, `node_modules/.cache`, `__pycache__`).

**Resolution.** L0 now means no builds or tests: the guard allows only
viewers, git reads, and `st` outside a workspace, and the docs say test runs
need L1. Evidence: `test_shell_outside_workspace_is_read_only` (`cargo test`,
`make` blocked at L0).

---

## Audit round 2 — 2026-10-07

Three independent auditor subagents, each with a clean context and a narrow
brief, probed the v0.2 guard: tool calls, shell, and ledger tampering. The
shell auditor did not return results, so its probe list was run by hand.

| # | Finding | Severity | Fix | Regression test |
|---|---|---|---|---|
| A-1 | Unknown tool names (`Write`, `write `, `@builtin/write`, `str_replace`, `edit`) fell through to allow | High | Names normalized; any tool outside a known set is denied (fail closed); `write` checks `path`, `file_path`, `filePath` | `test_unknown_and_disguised_tool_names_fail_closed` |
| A-2 | `code` rewrite with `dry_run` omitted was treated as a read | Medium | Any `code` write operation is a write unless `dry_run` is explicitly `true` | `test_code_rewrite_is_a_write` |
| A-3 | `perl -pi` / `-0pi` escaped the in-place check; `git apply --directory=../../proj` was allowed | High | Combined short flags detected; every argument of an in-place editor, and of every mutating git subcommand run from a workspace, is checked against the main checkout | `test_inplace_flags_and_git_directory_options` |
| A-4 | Editing an order's unsigned `state` from `reported` to `dispatched` revived its authority | Medium | A filed report or verdict for the current attempt ends authority regardless of `state`; `st report` refuses a second report per attempt; `st dispatch` refuses an order with a signed accept/reject verdict; `st verify` flags the rollback | `test_rolled_back_state_does_not_restore_authority`, `test_accepted_order_cannot_be_rerun_by_editing_state` |

Correctly blocked in this round: forged, copied, replayed, and role-changed
approvals; standing-order level escalation; aliased and forged decision and
revoke records; private-key reads via path aliases; subagent stages without
an order or on path-traversal agent names; `cp -t`, `install -D`, `rsync`,
`ln -s`, `git -C`, `--git-dir`, `awk -i inplace`, `patch -d`, `tee`, quoting
and escape tricks (`r''m`, `\rm`, `$'…'`), brace and glob expansion, and fd
redirects into the main checkout.

Evidence: 55 unit tests pass; every confirmed probe was re-run against the
patched guard and blocked, with ordinary workspace controls still allowed;
`tests/scenarios.py` 5/5 after the fixes.

**Residual after round 2 (closed in v0.3, below).** Someone who could
rewrite unsigned ledger files *and* delete the report file could
re-activate an order the surgeon had signed, limited to that exact spec,
role, and authority.

---

## v0.3 — authority moves out of the repository

Root cause of A-4 and its residual: the guard derived live authority from
the ledger's `state` field, and the ledger is shared, unsigned, and
writable by anything that can write the repository. Checking more ledger
files (the round-2 fix) only moved the problem, since files can be deleted.

**Design.** Three properties, none of which depend on the ledger:

1. **Leases outside the repository.** `st dispatch` appends an `open`
   event to `~/.config/surgical-team/leases/<repo-hash>.jsonl`, binding
   order, attempt, role, spec hash, grant, and expiry. `st report`,
   `reclaim`, `cancel`, and verdicts append `close`. The guard grants
   authority only for an open lease whose spec, role, and grant still match
   and whose grant still verifies. The ledger's `state` is not consulted.
   The store is guard-protected like the trust root.
2. **One use per grant.** A grant (approval signature, or standing order
   plus exact spec) backs at most one reported attempt; `st dispatch`
   refuses a consumed grant. Retry after a report goes through `st revise`
   and a new signature.
3. **Approvals expire.** Signed payloads carry `not_after`
   (`st approve --for MINUTES`, default max(60, 3x budget)); leases inherit
   it. v0.2 approvals with no expiry are not honored.

**What this closes.** Rolling back state, deleting reports and verdicts,
planting orders under a valid standing order, swapping the spec or role
after dispatch, and a ledger pulled from another clone all grant nothing
now. Each case is a test in `TestLeases`.

**What remains, stated precisely.** Code an agent runs inside a workspace
runs as the surgeon's user, so it could edit the lease store too. That is
the documented sandbox boundary: such code can already write the main
checkout directly. What it gains through the lease store is bounded to a
grant the surgeon signed (exact spec, role, level) and ends at the
approval's expiry. It cannot sign, because `st setup` refuses keys that sign
without a passphrase, touch, or confirmation. The strong control remains a
container with the main checkout and `~/.config/surgical-team` read-only.

**Evidence.** 65 unit tests pass. `TestLeases` (10 tests) covers rollback
plus deleted report, missing lease, planted standing-order order, spec swap,
role swap, expiry on use and at dispatch, pre-0.3 approvals, revise and
re-approve, lease-store protection, and lease close on every exit. Mutation
check: putting back the v0.2 state-based authority makes 4 `TestLeases`
tests fail. Live: `tests/scenarios.py` 5/5; and a real `st-tester` agent given
the briefing of a reported order whose ledger was rolled back and whose
report was deleted was BLOCKED on its write, with the board showing `NO LIVE
LEASE HERE`.
