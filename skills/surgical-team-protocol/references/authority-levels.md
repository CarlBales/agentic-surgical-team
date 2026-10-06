# Authority Levels

The surgical team's safety model. Brooks' copilot could write code without
being responsible for any of it; the surgeon remained responsible. Authority
levels make that split explicit for agents.

An authority level answers one question: **how far can the blast radius of
this agent's actions reach?**

## L0 — Observe

Read and reason. Change nothing.

Permitted:

- Read files, list directories, search the codebase
- Run read-only commands: `git log`, `git diff`, `git status`, `cargo tree`,
  `ls`, test runs that do not write to the repo
- Fetch public documentation
- Produce analysis, options, and recommendations in the report

Forbidden:

- Writing any file in the project, including config and docs
- `git` commands that mutate state, including `add` and `stash`
- Installing packages, modifying lockfiles, or mutating a global toolchain
- Network calls that transmit project content anywhere

L0 is the default. Reviews, audits, option papers, and language-lawyer
opinions are normally L0.

## L1 — Draft

Produce work in isolation. The surgeon's checkout is untouched.

Adds to L0:

- Write files inside the designated workspace only, either
  `.surgical-team/scratch/<WO-ID>/` or a git worktree created for the order
- Run builds, tests, formatters, and linters inside that workspace
- Install dependencies scoped to that workspace when the order says so

Still forbidden:

- Writing anywhere outside the designated workspace, including the surgeon's
  working tree, `.git` internals, and the user's home directory
- Any commit or branch operation
- Mutating global state: system packages, global git config, default
  toolchain, shell profiles

An L1 order without a workspace is malformed. Decline it and ask.

**The clerk's exception.** The program clerk holds a narrow exception,
defined by this protocol and requiring no decision record: it writes
`.surgical-team/` (orders, reports, decisions, `STATUS.md`, journal)
directly in the project tree at L1, because the ledger is the team's record
and is useless if it only exists on a branch. The exception covers that
directory and nothing else. The clerk never writes source, config, or
documentation, and never commits — staging and committing the ledger is the
surgeon's.

## L2 — Stage

Put work where the surgeon can review and merge it.

Adds to L1:

- Create a branch named `st/<WO-ID>-<slug>` from the agreed base
- Commit to that branch, with messages prefixed by the order ID
- Push that branch, **only if the order explicitly permits a push**, and only
  to a remote already configured for this project. Be clear-eyed about what
  this means: on a public remote, a pushed branch is visible to the world
  immediately. It is still not a merge, a release, or an announcement, which
  is why it sits at L2 rather than L3 — but it is a real disclosure, so the
  surgeon grants it per order rather than by default. If the order is silent
  on pushing, commit locally and say the branch is ready to push.
- Pushing to any destination not already configured for this project is L3,
  without exception.
- Open a **draft** pull request describing the order and the report

Still forbidden:

- Merging, rebasing, or pushing anything to the mainline
- `--force` in any form, including `--force-with-lease`
- Marking a PR ready for review, approving, or requesting external review
- Touching branches other than the one created for this order
- Deleting any branch, including your own
- Tagging or releasing

## L3 — Accept

The surgeon's level. **No agent ever holds L3**, even by standing order.

L3 actions:

- Merging to the mainline; marking a PR ready; approving a PR
- Deploying, releasing, tagging, publishing a package
- `git push --force`, `reset --hard`, `clean -f`, history rewrites,
  branch deletion
- Dropping or truncating data stores; bulk deletes; destructive migrations
- Creating, rotating, revoking, or reading out credentials and secrets
- Changing authentication, authorization, or access controls
- Modifying infrastructure-as-code that affects live resources
- Anything that spends money or sends mail outside the team

If an order asks for an L3 action, respond `DECLINED` and name the action.
Offer the L2-equivalent instead: prepare the change, stage it, and describe
exactly what the surgeon has to run.

## Standing orders

The surgeon may pre-approve a class of work so routine orders don't need
per-order approval. A standing order is recorded as a `DEC-` entry and names
the role, the maximum authority, the budget ceiling, and the scope.

The program clerk's ledger-write exception, described under L1, is not a
standing order. It is part of this protocol and needs no `DEC-` record.

```
DEC-014  Standing order
Role       tester
Authority  up to L1
Budget     30 minutes, 50k tokens per order
Scope      Adding or extending tests for modules that already have tests
Expires    2026-12-31
```

Limits that always hold:

- A standing order can never grant L3.
- A standing order can never grant authority outside the named scope.
- A standing order can be revoked at any time; check `decisions/` for the
  current set rather than assuming last session's grants still apply.
- When in doubt whether work falls inside a standing order, it does not.
  Ask.

## Irreversibility test

Before any action not explicitly permitted by your level, ask:

1. **Can I undo this with a single local command?** If yes, it is probably
   within L1/L2.
2. **Who or what acts on it once I've done it?** A branch or draft PR is
   normally inert: it can be read, but no user upgrades and no service
   redeploys because of it. Check that assumption before relying on it —
   push-triggered CI, preview deployments, mirrors, bots, and notification
   webhooks all turn a push into an action. If a push only publishes a
   branch, it is L2 with the order's permission. If it triggers a
   deployment, a release, or an outbound message, it is L3. A merge, a
   release, a published package, a posted comment, or a message to a
   stakeholder is always L3.
3. **Could this destroy work that is not reproducible?** If yes, it is L3.
4. **Does it touch credentials, access control, money, or production?**
   If yes, it is L3.

If you cannot answer confidently, treat the action as L3 and escalate. The
cost of asking is one round trip. The cost of a wrong irreversible action is
the surgeon's trust in the whole team.
