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
briefing.

The trust root is the surgeon's `allowed_signers` file, and live authority is
recorded in `leases/`. Both are in `~/.config/surgical-team/`, outside every
project and protected by the guard.

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

## What the guard cannot catch

The guard parses tool calls; it does not sandbox processes. It denies any
tool it does not recognize, refuses anything it cannot resolve (variable or command expansion in a path or
directory, `xargs` feeding a mutator, `popd`), recurses into `sh -c`, and
from inside a workspace refuses any command argument that names the main
checkout, the control plane, or key material. Outside a workspace it allows
only read-only viewers, git reads, and `st`.

Anyone who can write the repository but is not running as you (a pull
request, a teammate's clone, a compromised mirror) cannot create
authority. Leases are local and every grant is signed, so whatever they put
in `.surgical-team/` stays inert here.

What remains: a program run inside a workspace (a build script, a test, a
script the agent wrote there) runs as you and can do anything you can,
because the guard sees only its command line. That is the sandbox boundary,
and it already includes writing the main checkout directly, so the ledger is
not its easiest target. What it cannot do is sign. Any authority it could
revive by editing the lease store is limited to a grant you signed: that
exact spec, role, and level, and only until the approval expires. `st setup`
refuses keys that sign without a passphrase, touch, or confirmation, so the
signatures stay out of its reach.

If that residual risk matters for a project, run the team in an OS sandbox
or container with the main checkout mounted read-only. That is the strong
control; the guard is the cheap one.

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
