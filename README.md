# The Surgical Team

A proof-of-concept agent team modeled on Harlan Mills' *chief programmer team*,
as described by Frederick P. Brooks Jr. in "The Surgical Team" (chapter 3 of
*The Mythical Man-Month*, 1975).

The surgeon is a human. Everyone else on the team is an agent, and a small
deterministic control plane (`st`) keeps the books and enforces the rules.

## The idea

Brooks starts from a dilemma. Conceptual integrity calls for a few good minds
doing design and construction. Large systems call for lots of manpower. How do
you reconcile those two needs?

Mills' answer was to organize each team like a surgical team, not like a
hog-butchering team. One person does the cutting, and everyone else supports
them so they're as effective and productive as possible. A team of about ten
people works as one mind because:

1. The problem is not divided. The surgeon and copilot both know all of the
   design and all of the code.
2. The relationship is superior to subordinate, not peer to peer. There's
   nothing to negotiate, because the surgeon decides.

Most of the 1975 cast (secretaries, keypunch logistics, a dedicated clerk) was
long ago absorbed by better tools or by programmers themselves. The structure
still holds, though, and it describes AI augmentation well: the human keeps
authority and conceptual integrity, and agents provide "all conceivable
support." Brooks summed it up as *few minds, many hands*. Agents give you the
hands without diluting the mind, provided the hands are tools and not more
minds to coordinate.

## Role mapping

| Brooks (1975) | This system | Kind | Definition |
|---|---|---|---|
| Surgeon (chief programmer) | The user | Human | [SURGEON.md](SURGEON.md) |
| Copilot | Design partner, critic, front channel, the only dispatcher | Agent `st-copilot` | [copilot](skills/copilot/SKILL.md) |
| Administrator (+ secretary) | IDs, validation, workspaces, dispatch, status | Tool | [`st`](bin/st) |
| Program clerk | The ledger: orders, reports, checks, decisions | Tool | [`st`](bin/st) |
| Editor (+ secretary) | Turns surgeon drafts into finished docs | Agent `st-editor` | [editor](skills/editor/SKILL.md) |
| Toolsmith | Dev environment, scripts, CI, tools for the team | Agent `st-toolsmith` | [toolsmith](skills/toolsmith/SKILL.md) |
| Tester | Adversary from the spec, plus scaffolding and data | Agent `st-tester` | [tester](skills/tester/SKILL.md) |
| Language lawyer | Interchangeable language specialist: Rust, TypeScript, Python, C# | Agent `st-language-lawyer-<lang>` | [language-lawyer-typescript](skills/language-lawyer-typescript/SKILL.md), … |
| Language lawyer, for "the operating systems the software had to run on" | Platform specialist (React Native / Expo first) | Agent `st-platform-lawyer-react-native` | [platform-lawyer-react-native](skills/platform-lawyer-react-native/SKILL.md) |
| Copilot as critic, made independent | Clean-context review of a pinned commit range; lenses for security, infrastructure, accessibility | Agents `st-reviewer`, `st-security-reviewer`, `st-infra-reviewer`, `st-accessibility-reviewer` | [reviewer](skills/reviewer/SKILL.md), … |
| *(new)* | Analysts that grade evidence: legacy behavior, incidents | Agents `st-archaeologist`, `st-incident-analyst` | [archaeologist](skills/archaeologist/SKILL.md), [incident-analyst](skills/incident-analyst/SKILL.md) |
| Program clerk (the judgment half) | Keeps a structured knowledge vault consistent | Agent `st-archivist` | [archivist](skills/archivist/SKILL.md) |
| *(new)* | Shared rules every agent follows | Protocol | [surgical-team-protocol](skills/surgical-team-protocol/SKILL.md) |
| *(new)* | Authority enforcement on every tool call | Hook | `st guard` |

### What changed from 1975

- **The administrator and clerk became a tool.** Their duties (numbering,
  validating, tracking state, creating workspaces, keeping status) are
  functions. An LLM doing them is slow, nondeterministic, and can corrupt
  the record. `st` does them atomically. Mills' point about the clerk
  survives intact: recording the work is what makes it public practice. It
  just doesn't need a mind.
- **The copilot is the front channel and the dispatcher.** It holds the
  session with the surgeon and is the only agent that starts other agents.
  (Kiro subagents cannot spawn subagents, so a separate dispatcher could not
  work anyway; on the Cursor Agent CLI, the guard refuses it.) Correspondence,
  secretaries' old job, is the copilot's.
- **Agents may write code; only the surgeon accepts it.** Brooks let the
  copilot write code without being responsible for any of it. That now
  covers every agent, and it is enforced: agents work in worktrees outside
  the repository, a guard hook confines them to their order's authority,
  and approvals and verdicts carry the surgeon's signature.
- **The language lawyer is a slot, not a person.** Any
  `language-lawyer-<lang>` skill satisfying the
  [contract](skills/surgical-team-protocol/references/language-lawyer-contract.md)
  fills it.

## Architecture

```
            ┌──────────────┐  st approve / accept / decide / grant   (signed)
            │   SURGEON    │──────────────────────────────────────────────┐
            └──────┬───────┘                                              │
                   │ conversation                                         ▼
            ┌──────▼───────┐   st draft / dispatch / check      ┌──────────────────┐
            │  st-copilot  │───────────────────────────────────▶│ st (control      │
            └──────┬───────┘                                    │ plane) + ledger  │
                   │ one subagent per dispatched order          │ .surgical-team/  │
   ┌───────────┬───┴───────┬──────────────┐                     └────────▲─────────┘
┌──▼───────┐┌──▼────────┐┌─▼────────┐┌────▼───────────────┐              │
│st-tester ││st-toolsmith││st-editor ││st-language-lawyer-*│── st report ─┘
└──────────┘└───────────┘└──────────┘└────────────────────┘
        every tool call of every agent ──▶ st guard (preToolUse) ──▶ allow / block
```

A work order is the only way work enters the team, and each dispatch gets
exactly one report. `st check` re-runs the order's executable acceptance
criteria in the workspace, so the surgeon judges the work against an
independent record, not only against the agent's own account.

## Repository layout

```
the-surgical-team/
├── README.md, GETTING-STARTED.md, SURGEON.md
├── bin/st                       # launcher for the control plane
├── src/surgical_team/           # control plane, guard (Kiro and Cursor adapters), agent installer (Python stdlib)
├── schema/                      # JSON Schemas for every ledger record: the on-disk contract
├── tests/test_*.py              # unit tests by module (tests/run.py runs them in parallel)
├── tests/guard-cases/           # guard conformance corpus (JSON): the guard's spec
├── tests/guard_corpus.py        # runs the corpus against any st binary (--st PATH)
├── tests/scenarios.py           # behavioral scenarios: real agents, assertions on state
├── docs/findings.md             # the v0.1 review and how each finding was resolved
├── scripts/validate-skills.sh   # Agent Skills structural validation
├── scripts/check                # the local gate; installed as the pre-push hook
├── scripts/publish              # scanned snapshots to a public remote; never the history
├── .github/workflows/ci.yml     # CI: Linux tests (py3.9, 3.13), types, lint, coverage; pull requests on github.com
└── skills/
    ├── surgical-team-protocol/  # shared rules; references/ and JSON templates in assets/
    ├── copilot/
    ├── editor/
    ├── toolsmith/
    ├── tester/
    ├── language-lawyer-{rust,typescript,python,csharp}/
    ├── platform-lawyer-react-native/
    ├── reviewer/, security-reviewer/, infra-reviewer/, accessibility-reviewer/
    ├── archaeologist/, incident-analyst/
    └── archivist/
```

## Using it

Requires Python 3.9+ (it runs on the Python that ships with macOS), git,
and OpenSSH 8.1+ (for `ssh-keygen -Y`). The team runs on Kiro CLI or the
Cursor Agent CLI; install for either or both. Cursor team sessions are
supported and verified on the Cursor Agent CLI only. Do not run them in the
Cursor IDE until it is verified: this project's IDE session did not route its
tool calls through user-level hooks, so the guard may be absent (see
[Limits and open questions](#limits-and-open-questions)).

```bash
export PATH="$PWD/bin:$PATH"
st setup --key ~/.ssh/id_ed25519 --identity you@example.com   # key must need a passphrase, touch, or confirm
st doctor                                                     # check versions, key policy, installed agents, ledger
```

Don't load the team's skills into a general-purpose agent: they assume the
guard and the ledger exist. [GETTING-STARTED.md](GETTING-STARTED.md) walks
through a first session on an existing project and on a new one. The full
working flow is in [SURGEON.md](SURGEON.md).

### Kiro CLI

```bash
st install                       # one guarded ~/.kiro/agents/st-<role>.json per role skill
cd ~/code/your-project
st init --default-standing
kiro-cli chat --agent st-copilot
```

Each `st-<role>` agent loads only the protocol and its own role skill, and
runs every tool call through `st guard --role <role>`.

### Cursor Agent CLI

```bash
st install --host cursor         # ~/.cursor/agents/st-<role>.md, the /st command, and the guard hook
cd ~/code/your-project
st init --default-standing
agent "/st"                      # supported Cursor team-session entry point
```

> **Cursor team sessions are supported and verified on the Cursor Agent CLI only.**
> Do not run them in the Cursor IDE until it is verified: this project's IDE
> session did not route its tool calls through user-level hooks, so the guard may
> be absent (see [Limits and open questions](#limits-and-open-questions)).
>
> **Never use Cursor cloud/background agents on a team project.** They do not
> load the user-level guard at `~/.cursor/hooks.json`, run early read-only turns
> without hooks, and do not fire `sessionStart`, so neither the guard nor role
> binding is present. Use the local Cursor Agent CLI instead.

Cursor's hooks are global and its subagents can't carry their own, so the
install works differently from Kiro:

- **A team session is opt-in per Agent CLI chat.** From the main checkout, run
  `agent "/st"` and it is the copilot: the installed command carries the
  copilot prompt, the protocol, and the copilot skill, and tells it to run
  `st status` and scrub in. Every other Agent CLI chat rooted in the main
  checkout is ordinary Cursor: the guard stays out, except that a plain chat
  cannot launch `st-<role>` agents. The namespace check ignores surrounding
  whitespace and case, so spelling variants enter the same guarded path. A
  top-level chat rooted in `../<repo>.st/WO-…/` is always
  refused, even if it opens with `/st`; open the main checkout instead. An
  order workspace belongs only to the specialist dispatched there.
- **Specialists are subagents.** `st-<role>.md` carries the role prompt with
  the protocol and role skill inlined, so re-run `st install --host cursor`
  after editing a skill (`st doctor` flags out-of-date files).
- **Installation preserves other hooks.** It replaces only the entries owned
  by `st` and keeps every other entry in each event list. If `hooks` is not an
  object or an event is not a list, installation refuses to rewrite
  `hooks.json` and asks you to fix it by hand first.
- **One hook guards every tool call** (`st guard --host cursor`, with
  `failClosed`). It works out the role from bindings it keeps under the
  trust root:
  - In the main checkout, a chat that opens with `/st` binds as the copilot;
    any other chat binds as plain. Only the surgeon can type a chat's first
    message. A top-level chat whose cwd or window root is an order workspace
    binds as refused instead, regardless of its first message.
  - A subagent binds to the role it was launched as. The copilot's `Task`
    call must carry exactly one dispatched order's briefing, and the
    subagent claims that dispatch once, when its transcript opens with the
    same prompt.
  - An unbound conversation in, or targeting, a ledger project is refused.
  - Outside team projects the guard allows everything, so ordinary Cursor
    use elsewhere is unaffected.

  The exact rules (ambiguous claims, missing context, state expiry, the
  output-spill exception) are in
  [authority levels](skills/surgical-team-protocol/references/authority-levels.md).
- The copilot can launch only `st-<role>` subagents, so Cursor's built-in
  explore and generalPurpose subagents are refused, as they are on Kiro.
- Cursor Agent CLI approval settings still apply on top of the guard; the live
  scenarios use `--force`.

### Footprint and removal

The team is optional, and nothing in the project depends on it. Teammates
without `st` see a `.surgical-team/` directory and nothing else.

| What | Where | Removed by |
|---|---|---|
| The ledger (committed, shared) | `.surgical-team/` | `git rm -r .surgical-team` |
| Order workspaces | `../<repo>.st/WO-…/` (git worktrees) | A verdict or `st cancel`, when the worktree is clean; `st prune [--force]` |
| Order branches | `st/WO-…` | `st prune`, after a verified signed rejection/cancellation, or a verified acceptance once merged |
| Agents, hooks, `/st` | `~/.kiro/agents`, `~/.cursor/{agents,commands,hooks.json}` | `st uninstall [--host kiro\|cursor]` |
| Trust root | `~/.config/surgical-team/` | by hand |

An accepted L1 order's work is uncommitted files in its worktree, so the
worktree stays until you have taken what you need. `st prune` treats the
ledger's terminal state as untrusted: it removes an order worktree or branch
only when the matching surgeon-signed verdict or cancellation verifies (and
an accepted branch is merged). `st prune --dry-run` shows what would go, and
`st doctor` reports the footprint.

## Verification

Validation runs locally, before every push. Install the hook once per clone:

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
scripts/check --install-hook            # .git/hooks/pre-push, main checkout only
```

On each push the hook checks every pushed commit in a clean clone (never the
working tree): ruff, mypy, skills, the unit suite on your Python and on the
3.9 floor if `/usr/bin/python3` is 3.9 (macOS), the black-box suite, guard
latency, and mutation testing of the guard files the push changes.

A push that changes `src/`, `bin/`, `skills/`, or `tests/scenarios.py` also
needs the live scenarios, once on each host whose CLI is installed. They take
about 20 minutes and spend tokens, which outlasts the connection git opens to
the remote before the hook runs, so push those changes with
`scripts/check push`. It runs the whole gate first, records the commit as
checked, and then runs `git push`. A plain `git push` of such a change is
refused at once with that advice. `ST_SKIP_SCENARIOS=1 git push` pushes
without the scenarios, and `ST_SKIP_CHECK=1 git push` skips the whole gate.

```bash
scripts/check push [ARGS]               # the gate with live scenarios, then git push ARGS
scripts/check                           # the push gate on the working tree
scripts/check --commit HEAD             # the push gate on a commit, in a clean clone
scripts/check --full                    # + branch coverage (>= 85%) and full mutation testing
scripts/check --linux                   # + the suite on Linux, py3.9, in podman or docker
scripts/check --scenarios --runs 3      # + live scenarios, 3 runs each
```

CI (`.github/workflows/ci.yml`) keeps only what a laptop cannot vouch for:
the suite on Linux at Python 3.9 and 3.13, plus types, lint, skills, and
coverage, for pull requests from contributors whose hooks did not run.
Hosted runners are free for public repositories on github.com, so it runs on
every pull request there; on any other server it runs only when started by
hand. macOS, latency, mutation testing, and live scenarios are local only.

### Publishing

The development repository's history is never pushed to a public remote.
`scripts/publish` exports `HEAD` with `git archive`, so `export-ignore` paths
stay out. It scans every exported path and line, plus the commit message, for
keys, tokens, home directories, personal email addresses, confidentiality
markers, and a private denylist (`.git/info/publish-denylist`, never
committed). If the scan is clean, it commits the snapshot on top of the public
branch under a public identity, runs the gate on that exact commit, and pushes
it. The pre-push hook refuses anything else on a public remote, even with
`ST_SKIP_CHECK=1`. Setup is in `scripts/publish --help`.

```bash
scripts/publish --scan                  # what would ship, scanned; changes nothing
scripts/publish --dry-run               # also build the public commit
scripts/publish -m "Update to 0.6.1"    # build, gate, push
```

The pieces, individually:

```bash
python3 tests/run.py                    # unit tests + guard corpus, parallel, ~10 s (no model calls)
python3 -m unittest discover -s tests   # the same tests, serially
ST_TEST_MODE=subprocess python3 tests/run.py   # the same tests, black-box against bin/st
python3 tests/guard_corpus.py           # just the guard corpus; --st PATH checks another build, --host cursor|all
python3 tests/mutate_guard.py           # host-neutral + Cursor guard mutation testing (slow)
scripts/validate-skills.sh              # skills against the Agent Skills spec
python3 tests/scenarios.py --runs 3     # live agents via kiro-cli, pass rate over 3 runs; spends tokens
python3 tests/scenarios.py --host cursor   # the same scenarios via the Cursor CLI (agent -p)
```

The unit suite runs the guard corpus twice, once as Kiro events and once as
Cursor events through the Cursor adapter, each bound to the case's role. The
mutation harness first checks an unmodified copy, then mutates host-neutral
refusals, Cursor role-resolution and response refusals, session expiry and
claim gates, and both hosts' deny-response gates. It reports killed/total for
each source file; an equivalent survivor requires an explicit source-keyed
rationale in the harness.

Unit tests run `st` in-process by default (`tests/support.py`), which is
what makes them fast. The same tests run unchanged as a black box against
any build with `ST_BIN=/path/to/st`, which is how a port would be checked.
Coverage and lint tools are pinned in `requirements-dev.txt`; `st` itself
has no dependencies.

The scenarios assert on what happened (ledger state, the filesystem, the
filed report), never on what the model said in conversation: a tester told
to edit the main checkout leaves it clean, a tester with no spec reports
`BLOCKED`, a blind tester finds the spec violation it cannot see in the
code, the copilot cannot approve its own order, a reviewer catches a
dropped check in a pinned range, a security reviewer cites CWE-89 without
echoing the planted key, a TypeScript lawyer labels a floating promise
WRONG, an incident analyst with no evidence reports `BLOCKED`, a reviewer
launched with a tester's briefing embedded leaves the tester's workspace
untouched, and, on Cursor only, an unrelated chat keeps working while a team
dispatch is pending and a chat not started with `/st` edits the main checkout
but cannot launch the team.

## Limits and open questions

- **Authority lives outside the repository.** The guard trusts only
  signatures and a local lease store, never the ledger's state, so a forged
  or rolled-back ledger, or one pulled from another clone, grants nothing.
  Approvals expire, and each one backs at most one reported attempt. Decision
  text is separately signed: briefings withhold content from unverified or
  missing records, and an order naming one as binding cannot dispatch.
- **The guard is a parser, not a sandbox.** It confines where agents write
  and what they run outside a workspace. For every role it also refuses known
  agent-host CLIs when they appear directly or through modeled shell/package
  wrappers, preventing a specialist from starting an unbound host session.
  That check is a speed bump for well-behaved models, not a boundary: a build
  script run inside a workspace can still do anything the user can, including
  start another program. Direct agent writes to any `.git` path inside a
  workspace are denied, and `st` verifies linked-worktree metadata from the
  main checkout before its own Git commands, so a planted workspace gitfile is
  refused rather than executed. That does not make workspace programs safe.
  For hostile code, `scripts/sandbox` disables the
  network and keeps the main checkout's source and history, the git hooks and
  config, and signer configuration read-only, while the team's own state stays
  writable. The boundary is in
  [authority levels](skills/surgical-team-protocol/references/authority-levels.md).
- **Budgets are estimates.** Nothing in the team can interrupt a running
  subagent; hard limits come from the host. `st` records actual wall clock
  and flags overruns and stale dispatches.
- **Two hosts: Kiro and Cursor.** The guard's reasoning is host-neutral (a
  normalized tool event in, allow or deny out). Each host's hook format
  lives in one adapter (`src/surgical_team/guard/hosts.py`), and Cursor's
  role binding lives in `guard/cursor.py` and `guard/sessions.py`. Another
  host with a pre-tool hook is a new adapter plus a run of the guard corpus
  through it.
- **Cursor MCP events omit server identity.** A recorded local CLI
  `preToolUse` payload named the tool `MCP:<tool>` and supplied only its
  arguments; it did not include the configured MCP server. Source grants
  therefore use the host's exact raw name (`@server/tool` on Kiro,
  `MCP:<tool>` on Cursor), with no basename conversion. Cursor cannot
  distinguish two configured servers that expose the same tool name; avoid
  such collisions because an exact `MCP:<tool>` grant necessarily covers
  either one.
- **Cursor cloud/background agents are not guarded.** They do not load the
  user-level hook installed by `st`, run early read-only turns without hooks,
  and do not fire `sessionStart`. Never use them on a team project; use the
  local Cursor Agent CLI. Cursor does load project
  `.cursor/hooks.json` hooks in writable cloud turns, so a future mode could
  install there if `st` were present on the cloud VM, but it is not
  implemented and could not cover the early reads or missing session binding.
- **Cursor's role binding rests on observed behavior, in the CLI only.**
  Recorded CLI payloads (Cursor Agent CLI 2026.10.01 and 2026.10.14) show
  three things the docs don't promise:
  - a subagent's tool calls carry their own `conversation_id`;
  - its transcript exists, opening with its Task prompt, before its first
    tool call;
  - `subagentStart` and `subagentStop` never fire, so the guard can't rely
    on them.

  A top-level chat rooted in an order workspace is persisted as refused, not
  plain or copilot; open the main checkout for either kind of top-level chat.
  The deterministic workspace layout still identifies that context if the
  worktree's Git metadata is unreadable. If the first two observations change,
  the guard refuses the subagent rather than guessing its role. The binding
  trusts the transcript opening, which only Cursor writes (`~/.cursor` is
  guard-protected). The one way around it is the
  surgeon pasting a pending briefing into a new chat, which no agent can do.
  `EditNotebook` reaches the hook as a `Write`, so notebook edits are guarded.

  **Cursor team sessions are supported and verified on the Agent CLI only.**
  Do not run them in the Cursor IDE until it is verified. This review's IDE
  session did not route its own tool calls through user-level hooks, so an IDE
  team session may have no guard at all. Recorded CLI events carry no documented
  or observed surface field that distinguishes the Agent CLI from the IDE, and
  the guard cannot detect a session when the host invokes no hook. Future work is
  to re-exercise IDE hooks and add fail-closed surface detection only if Cursor
  exposes a reliable discriminator. Evidence is in
  [docs/review-2026-10-13.md](docs/review-2026-10-13.md); the rules are in
  [authority levels](skills/surgical-team-protocol/references/authority-levels.md).
- **Blind orders block content, not names.** A direct read of a withheld path
  is denied, as is a content search rooted above one, even with an include or
  glob filter. Directory listings and filename-only globs remain available.
  Ledger context is recovered from tool targets when the cwd has none, with
  inherited `GIT_*` routing removed. Main checkouts and verified linked
  worktrees are supported; if a checkout containing `.surgical-team/` uses an
  unsupported submodule or `--separate-git-dir` layout, the guard refuses the
  call instead of treating it as a non-team directory. The details are in
  [authority levels](skills/surgical-team-protocol/references/authority-levels.md).
- **The scenario suite is small.** Twelve scenarios (ten on Kiro) cover the
  authority boundaries (including a combined-briefing dispatch and, on Cursor,
  plain chats beside the team) and six role behaviors; most roles
  have none yet. Model behavior varies: run them several times (`--runs 3`)
  before trusting a change to a prompt, and add a scenario whenever a role
  misbehaves.
- **Checks run trusted commands.** `st check` executes the order's `check`
  strings. The guard only lets an agent trigger them when the surgeon signed
  that exact spec; under a standing order, the surgeon runs `st check`.
- **Multiple surgeons.** Brooks' answer was a system architect above the
  surgeons. Here that would be multiple signers with scoped trust, not yet
  designed.

## Sources

- Brooks, F. P. Jr. *The Mythical Man-Month*, ch. 3 "The Surgical Team."
  Addison-Wesley, 1975; anniversary ed. 1995.
- Mills, H. "Chief programmer teams: principles and procedures." IBM Federal
  Systems Division Report FSC 71-5108, 1971.
- Agent Skills specification: <https://agentskills.io/specification>
