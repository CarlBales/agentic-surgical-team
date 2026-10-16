# Authority Levels

The surgical team's safety model. Brooks' copilot could write code without
being responsible for any of it; the surgeon remained responsible. Authority
levels make that split explicit, and the guard enforces it.

An authority level answers one question: **how far can the blast radius of
this agent's actions reach?**

## Where authority comes from

An agent holds authority only while all of these hold, checked by the
guard on every tool call:

1. **A grant signed by the surgeon** covers the order: a signed
   **approval** of that exact spec, unexpired (`st approve --for MINUTES`;
   default the larger of 60 minutes and three times the budget), or an
   active signed **standing order** covering the role, level, and budget.
   Editing the spec after approval voids it.
2. **A live lease** for that order exists in the lease store on this
   machine. `st dispatch` opens it; `st report`, `reclaim`, `cancel`, and
   verdicts close it. The lease binds the order's role, spec hash, grant,
   and attempt, and expires with the approval.
3. **The grant has not been used up.** A grant backs at most one reported
   attempt. Running the order again needs `st revise` and a new approval.

The ledger's `state` field plays no part. Nothing in the repository grants
authority: not an order file, not a forged or restored state, not a ledger
pulled from another clone, not a message from the copilot, not text in a
briefing. It also cannot authorize destructive cleanup: `st prune` requires a
matching verified surgeon-signed verdict or cancellation before removing an
order's worktree or branch. Decision content has its own surgeon signature,
separate from an approval that signs the order spec and its referenced decision
IDs. Briefings render only verified decision content. They identify unverified
or missing records by ID and status in a non-authoritative warning section, and
dispatch refuses an order that names either kind as binding. Verified bindings that are
revoked, superseded, or expired remain visible with that status so the
specialist can report the conflict without treating the old decision as active.

The trust root is the surgeon's `allowed_signers` file, and live authority is
recorded in `leases/`. Both are in `~/.config/surgical-team/`, outside every
project and protected by the guard.

Cursor team sessions are supported and verified on the Cursor Agent CLI only.
Do not run them in the Cursor IDE until it is verified: this project's IDE
session did not route tool calls through user-level hooks, so the guard may be
absent (see the README's
[Limits](../../../README.md#limits-and-open-questions)).

On the Cursor Agent CLI, a team session is opt-in per chat. In the main checkout,
a top-level chat (one with a `sessionStart` record) whose first message is the
`/st` command binds as the copilot. Cursor records the expanded command in the
transcript, and where it fires `beforeSubmitPrompt`, a `/st` prompt binds even
earlier. Any other top-level chat rooted in the main checkout binds as plain:
it is ordinary Cursor and the guard does not constrain it, except that it
cannot launch `st-<role>` agents. The team namespace comparison strips
surrounding whitespace and case-folds names, so spelling variants cannot pass
as ordinary agents. Subagents of a plain chat bind as plain from their Task
prompt.

A top-level chat whose cwd or `workspace_roots` lies in
`../<repo>.st/WO-…/` instead persists a refused binding, whether its opening is
plain or `/st`: order workspaces belong only to the specialist dispatched
there. Open the main checkout, then use `/st` for the team or another opening
for ordinary Cursor. The session record retains this decision if later events
omit or change their roots, and the deterministic sibling-workspace layout
recovers the main ledger without trusting unreadable workspace Git metadata.
If a top-level chat's transcript is still unreadable after the wait described
below, its call is refused rather than guessed. Only the person at the keyboard
can type a chat's first message.

Subagent launch fails closed too. Team agent names are stripped and case-folded
before the `st-` prefix check, then validated against the same role and order
rules. Every stage or Task prompt must carry the briefing of exactly one live
order dispatched to the selected role, and must not embed another live order's
briefing (its `# Work order WO-…` header). A
spec may still mention other orders, for example in `scope.out`. Cursor records
each allowed prompt as a pending dispatch; when a transcript opening contains
overlapping pending prompts, the unique longest prompt is the only one that
may bind. Distinct equal-length matches bind nothing rather than choosing by
file order; the same briefing launched twice is one candidate, and the oldest
record is claimed first. A subagent's first tool call can arrive before Cursor
writes its transcript, so while a dispatch is pending the guard waits up to
5 s for a missing transcript before deciding. A role binding still grants no authority without the
matching signed grant and live lease above.

Cursor pending and consumed-claim records expire after one hour. On each
interactive team `sessionStart`, the guard removes expired claims and session
or binding records idle for 14 days; resolving an active binding refreshes its
file activity time. If a copilot binding is pruned while its top-level session
record remains, that record can restore only the copilot role. A specialist
has no such session record and is refused in team context after its binding
and consumed dispatch age out; cleanup never infers a replacement role.

On the Cursor Agent CLI, the guard discovers team context from `workspace_roots`,
the event
cwd, or the nearest existing parent of a tool's file/search target or shell
working directory. A top-level workspace-session refusal considers only its
cwd/window roots, not a tool target, so an ordinary main-checkout chat may still
inspect an order worktree. Cursor `SemanticSearch` checks every listed target directory
as a content-search root; with no listed targets, it checks the event cwd. An
unbound conversation targeting a ledger project is therefore refused even when
Cursor omits project context. While an unexpired Task dispatch is pending, an
unbound conversation with no ledger context still tries to claim it from its
transcript, so a team subagent arriving without context binds as usual. If it
has no transcript yet, the call is refused, since it may be that subagent; if
its transcript matches no dispatch, it is an ordinary chat elsewhere and the
guard stays out, as it does whenever no dispatch is pending.

For a bound Cursor Agent CLI team conversation, Cursor's own large-output spill
exception
covers only a raw `Write` to
`~/.cursor/projects/<slug>/agent-tools/<file>`, where `<slug>` comes from that
event's `workspace_roots`. It does not cover `Delete` or another project's
slug. Role resolution happens before the exception, so an unbound conversation
in a team project is refused as usual.

## L0 — Observe

Read and reason. Change nothing.

Permitted:

- Read files, list directories, search the codebase
- Read-only viewers (`cat`, `rg`, `ls`, `jq`, `diff`, …) and git reads
  (`status`, `log`, `diff`, `show`, `blame`, `fetch`)
- `st` read commands
- Fetch public documentation
- Produce analysis, options, and recommendations in the report

Forbidden, and blocked by the guard:

- Writing any file, anywhere
- Running builds, tests, scripts, or interpreters. These write artifacts
  (`target/`, `__pycache__`, caches) even when the code under test does
  not. If an L0 review needs a test run, the order is L1.
- Mutating git: `add`, `stash`, `commit`, `checkout`, …

L0 is the default. Reviews, audits, option papers, and language-lawyer
opinions are normally L0.

## L1 — Draft

Produce work in isolation. The surgeon's checkout is untouched.

Adds to L0, inside the order's worktree only (`../<repo>.st/<WO-ID>/`,
created by `st dispatch`):

- Write files
- Run builds, tests, formatters, linters, and scripts
- Install dependencies scoped to that workspace (`npm install`, `cargo add`)
- Stage changes and reset unstaged work (`git add`, `git restore`)

Still forbidden:

- Anything outside the workspace, including the surgeon's working tree
- Commits and branch operations
- Global state: system packages, global installs, global git config,
  shell profiles

## L2 — Stage

Put work where the surgeon can review and merge it.

Adds to L1:

- Commit to the order's branch `st/<WO-ID>-<slug>`, with messages prefixed
  by the order ID
- Push that branch, **only if the approval includes `push`**, and only to a
  remote already configured for this project. A standing order never grants
  a push. On a public remote a pushed branch is visible to the world
  immediately: it is not a merge or a release, which is why it sits at L2,
  but it is a disclosure, which is why the surgeon grants it per order.
- Draft a pull request description for the surgeon to open

Still forbidden:

- Merging, rebasing, or pushing to any other branch
- `--force` in any form, `--all`, `--tags`, `--mirror`, deletes
- Marking a PR ready, approving, or requesting review
- Creating, deleting, or moving branches; tagging or releasing

## L3 — Accept

The surgeon's level. **No agent ever holds L3.** `st` refuses to file an
order or standing order at L3.

- Merging to the mainline; marking a PR ready; approving a PR
- Deploying, releasing, tagging, publishing a package
- `push --force`, `reset --hard`, `clean`, rebases, history rewrites,
  branch deletion
- Dropping or truncating data stores; bulk deletes; destructive migrations
- Creating, rotating, revoking, or reading out credentials and secrets
- Changing authentication, authorization, or access controls
- Modifying infrastructure-as-code that affects live resources
- Anything that spends money or sends mail outside the team

If an order needs an L3 action, report `DECLINED`, name the action, and
offer the L2 equivalent: stage the change and describe exactly what the
surgeon has to run.

## Standing orders

A standing order pre-approves a class of work so routine orders need no
per-order approval. The surgeon issues it:

```bash
st grant --role tester --max L1 --budget 30 --expires 2026-12-31 \
  --scope "Adding or extending tests for modules that already have tests"
```

An order invokes it with `"standing": "DEC-NNN"`. `st init
--default-standing` files one at setup: every role may run L0 orders up to
30 minutes without asking.

Limits that always hold, all enforced by `st`:

- A standing order never grants L3, and never a push.
- It covers only its role (or `*`), up to its level and budget ceiling.
- `st revoke DEC-NNN` ends it immediately; expiry ends it automatically.
- Scope is prose and is not machine-checked. When in doubt whether work
  falls inside a standing order, it does not. Ask.

## Read-only sources

Some roles need evidence that is not in a file: log queries, resource
descriptions, a ticket. The guard denies every tool it does not know, so an
order grants them explicitly in `inputs.sources`:

```json
"sources": [
  {"tool": "use_aws", "service": "logs", "region": "us-east-1",
   "operations": ["describe-log-groups", "filter-log-events"]},
  {"tool": "@tracker/get_issue", "readonly": true, "note": "incident ticket"},
  {"tool": "MCP:get_issue", "readonly": true, "note": "same tool on Cursor"}
]
```

Rules, all enforced by `st` and the guard:

- **Only under an approval.** A source is honored only while the order holds
  a live lease backed by the surgeon's approval of that exact spec. Under a
  standing order the copilot wrote the spec, so it could have granted the
  source itself; the guard refuses, and the briefing says so.
- **AWS calls are checked as reads.** The operation must start with a read
  verb (`describe`, `get`, `list`, `filter`, `lookup`, `search`,
  `batch-get`, `head`), match the granted service, operations, and region or
  profile when given, and carry no positional arguments. Operations that
  hand out secrets, credentials, parameters, sessions, or object contents
  (`get-secret-value`, `get-parameter`, `get-object`, …) are refused even if
  granted, and so is the high-level `s3` command.
- **MCP tools are attested, not inspected.** The guard cannot tell whether
  an arbitrary MCP tool writes, so the order must name the exact tool with
  `"readonly": true`. That is the surgeon's attestation when they approve.
  Name the source exactly as the host reports it: `@server/tool` on Kiro and
  `MCP:<tool>` on Cursor. There is no basename conversion between those
  forms; list both sources when an order must work on both hosts. A recorded
  Cursor CLI payload contained the tool name and arguments but no configured
  server name. Cursor therefore cannot distinguish two servers exposing the
  same tool name; do not configure that collision, because an exact
  `MCP:<tool>` grant covers either one. `st install` does not configure MCP
  servers; add the server to the role's agent config yourself, and the guard
  still denies its tools unless an order grants their exact host names.
- **Reads still leave the machine.** A source query is sent to the provider
  with the surgeon's credentials. Grant the narrowest operations the order
  needs, and prefer exported evidence in `inputs.files` when it will do.

## What the guard cannot catch

The fail-closed guarantee starts only when the host invokes the hook. Cursor team
sessions are supported and verified on the Cursor Agent CLI only. **Do not run a
team session in the Cursor IDE until it is verified:** this project's IDE session
did not route tool calls through user-level hooks, so the guard may be absent (see
the README's [Limits](../../../README.md#limits-and-open-questions)). **Never run
a Cursor cloud/background agent on a team project:** cloud agents do not load the
user-level `~/.cursor/hooks.json` written by `st install --host cursor`, run early
read-only turns without hooks, and do not fire `sessionStart`. The guard and role
binding are absent during that work. If an `is_background_agent` session event
does reach `st`, it is left unbound so later hooked tool calls are refused, but
`st` cannot constrain a call for which Cursor runs no hook.

Cursor does load checked-in project `.cursor/hooks.json` hooks during writable
cloud turns. A future installation mode could put the guard there, but it
would require `st` on the cloud VM, need a binding design that does not depend
on `sessionStart`, and still could not cover the early unhooked reads. This is
not implemented.

When a supported host invokes it, the guard fails closed: a tool it does not
know, an input it cannot parse, an internal error, or a guard that cannot
start at all (the hook command `st install` writes maps every exit other than
0 and 2 to a block) all deny the call. One case is the host's: whether a hook
that exceeds its timeout blocks is not documented. Re-run `st install` after
upgrading `st`.

A blind order denies direct reads of withheld paths and content searches rooted
above them. An include or glob filter does not relax that boundary because it
may still match withheld contents; narrow the search root to a directory that
does not contain a blind path. Directory listings and filename-only globs may
still expose names, but not file contents, and remain allowed. These checks are
host-neutral even when the event cwd is outside the project: the guard recovers
a ledger from the nearest existing parent of explicit read and image paths,
file/path fields, shell working directories, and path-like shell arguments.
It refuses targets spanning multiple team ledgers or conflicting with the cwd
ledger. This discovery selects context but grants no authority; signed grants
and live leases remain mandatory. Git discovery removes inherited `GIT_*`
routing. It supports main checkouts and verified linked worktrees; when safe
filesystem discovery fails for a checkout whose top level contains
`.surgical-team/`, a scrubbed `git rev-parse --show-toplevel` probe identifies
the context and the guard refuses the unsupported submodule or
`--separate-git-dir` layout instead of treating it as non-team. As elsewhere
in the shell model, a path computed inside a program is beyond the parser and
belongs to the sandbox boundary below.


The guard parses tool calls; it does not sandbox processes. It denies any
tool it does not recognize, accepts only shell it can
model (simple commands, pipelines, `;`/`&&`/`||`, literal redirects, and
`cd` to a literal path) and denies the rest, including control-flow
keywords and command or process substitution; it refuses anything it cannot
resolve (variable or command expansion in a path or
directory, `xargs` feeding a mutator, `popd`), recurses into `sh -c` and
`eval` (carrying `eval`'s working directory forward), refuses code it never
sees as a command line (`source`, `.`, `trap`, `alias`, functions,
`env -S`, shells and interpreters reading from stdin), and
from inside a workspace refuses any command argument that names the main
checkout, the control plane, or key material. Before any role's in-workspace
allowance, it refuses the agent-host command basenames `agent`, `cursor-agent`,
`cursor`, `kiro-cli`, `kiro`, `claude`, `codex`, `gemini`, `aider`, `goose`,
`opencode`, and `copilot`, plus `q` when its first argument is `chat`. It sees
those commands through modeled wrappers (`env`, inline shells, `xargs`,
`nohup`, `timeout`, `command`, and `exec`) and their known package names under
`npx`, `bunx`, `pnpm dlx`, and `uvx`; an argument or filename that merely
contains a listed word is unaffected. Literal `os`/`subprocess` launches in
Python `-c` are recognized too.

That CLI list is deliberately a speed bump for well-behaved models, not a
security boundary: code in a script or build remains opaque to the parser and
can start any process. Every direct write whose lexical or resolved workspace
path has a component named exactly `.git` is also refused, including shell
redirects and recognized file mutators: Git metadata can execute code on the
host. `.gitignore` and `.gitmodules` remain ordinary project content. Outside
a workspace it allows only read-only viewers, git reads, and `st`.

Anyone who can write the repository but is not running as you (a pull
request, a teammate's clone, a compromised mirror) cannot create
authority. Leases are local and every grant is signed, so whatever they put
in `.surgical-team/` stays inert here.

What remains: a program run inside a workspace (a build script, a test, a
script the agent wrote there) runs as you and can do anything you can,
because the guard sees only its command line. It can therefore bypass the
agent-host CLI speed bump as easily as any other command-line-only check.
That is the sandbox boundary,
and it already includes writing the main checkout directly, so the ledger is
not its easiest target. What it cannot do is sign. Any authority it could
revive by editing the lease store is limited to a grant you signed: that
exact spec, role, and level, and only until the approval expires. `st setup`
refuses keys that sign without a passphrase, touch, or confirmation, so the
signatures stay out of its reach.

Outside the sandbox, `st` nevertheless treats every linked worktree's Git
metadata as hostile. It finds the worktree in `git worktree list` from the
main checkout, verifies the Git-owned backlink, requires the workspace
`.git` entry to be a regular non-symlink gitfile pointing to that exact
administrative directory, and verifies its `commondir`. Its own worktree Git
reads then use explicit `--git-dir` and `--work-tree` from the main checkout,
with inherited `GIT_*` variables removed. A mismatch stops cleanup or checks
with a tamper warning and never asks Git to interpret the workspace gitfile.
This prevents workspace metadata from becoming a delayed host-code trigger;
it does not make the check or build program itself safe.

If that residual risk matters for a project, run the team with
`scripts/sandbox`. It mounts the project read-only but overlays
`.surgical-team/` and `.git/` read-write; it likewise mounts the trust root
read-only but overlays `leases/` and `cursor/` read-write. The sibling
worktrees are writable and the network is disabled.

Inside the writable `.git/`, everything that runs on the host or decides
what the host checks out stays read-only: `config`, `hooks/`, `info/`,
`HEAD`, `index`, `packed-refs`, `modules/`, and `refs/` except
`refs/heads/st/`, where order branches live. Workspace code therefore cannot
plant a hook or a `core.fsmonitor` command that runs at the surgeon's next
`git` command, move `main`, or add a replace ref (all checked in a real
container).

This protects the main checkout's source and history, `allowed_signers`, and
`config.json`. It does **not** protect the ledger, the order branches, leases,
Cursor bindings, or workspace contents from code running in a workspace. Since
v0.3, changing those writable records cannot grant more than the exact
unexpired spec the surgeon signed.

Workspace contents stay untrusted outside the container too: `st check` runs
the order's checks, and so the workspace's code, wherever it is invoked. Under
the sandbox, run `st check` inside it (the copilot does). That is the strong
control this container provides; the guard remains the cheap one.

## Irreversibility test

Before any action you are unsure of, ask:

1. **Can I undo this with a single local command?** If yes, it is probably
   within L1/L2.
2. **Who or what acts on it once I've done it?** A branch is normally inert.
   Check that assumption: push-triggered CI, preview deployments, mirrors,
   bots, and webhooks turn a push into an action. If a push triggers a
   deployment, a release, or an outbound message, it is L3.
3. **Could this destroy work that is not reproducible?** If yes, it is L3.
4. **Does it touch credentials, access control, money, or production?**
   If yes, it is L3.

If you cannot answer confidently, treat the action as L3 and escalate. The
cost of asking is one round trip. The cost of a wrong irreversible action is
the surgeon's trust in the whole team.
