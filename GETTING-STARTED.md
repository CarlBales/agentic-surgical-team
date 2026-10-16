# Getting started

This guide takes you from nothing to a working session with the surgical team.
It covers two paths: bringing the team to an **existing project**, and using it
to **build a new one**. You are the surgeon. The agents are your support staff,
and `st` keeps the books. [SURGEON.md](SURGEON.md) is the full charter; this
guide is the practical route in.

The team is optional throughout. Nothing in your project depends on it, you can
work without it at any time, and `st uninstall` plus `git rm -r .surgical-team`
removes it.

## 1. Set up your machine (once)

You need Python 3.9 or later, git, OpenSSH 8.1 or later, and either Kiro CLI or
the Cursor Agent CLI. Cursor team sessions are supported and verified on the
Cursor Agent CLI only. Do not run them in the Cursor IDE until it is verified:
this project's IDE session did not route its tool calls through user-level
hooks, so the guard may be absent (see the README's
[Limits and open questions](README.md#limits-and-open-questions)).

```bash
git clone <this repo> ~/tools/the-surgical-team
export PATH="$HOME/tools/the-surgical-team/bin:$PATH"   # add to your shell profile

st setup --key ~/.ssh/id_ed25519 --identity you@example.com
st install                  # Kiro: ~/.kiro/agents/st-<role>.json
st install --host cursor    # Cursor Agent CLI only: subagents, /st, and the guard hook
st doctor                   # every row should be ok
```

Your signing key is the team's trust root: approvals, verdicts, and decisions
carry its signature, and no agent can produce one. `st setup` therefore
refuses a key that signs without you. Use a key with a passphrase, a hardware
key, or an `ssh-agent` key added with `ssh-add -c`.

## 2. The loop you will repeat

Every piece of work goes through a work order. The copilot does the
paperwork, `st` does the bookkeeping, and you make the decisions.

| Step | Who | What happens |
|---|---|---|
| Talk | you and the copilot | You describe the problem. The copilot challenges it, brings options, and recommends one. |
| Order | copilot | It drafts a work order (`st draft`): role, intent, scope, acceptance criteria with executable checks, and authority level. |
| Approve | you | `st approve WO-… [--level L1] [--push]`. L0 work under the default standing order needs no approval. |
| Dispatch | copilot | `st dispatch` creates the order's workspace and briefing, and the copilot launches the specialist with it. |
| Report | specialist | It files `st report` with status, evidence, and findings outside its scope. |
| Check | copilot | `st check` re-runs the acceptance checks independently; the board flags reports their checks contradict. |
| Verdict | you | `st accept`, `st reject -m "why"`, or `st defer`. |
| Merge | you | You take the work into your branch. Only you merge. |

**Authority levels.** Pick the lowest one that does the job:
- **L0, observe:** read and report; nothing is written. This is the default for reviews, audits, and option papers.
- **L1, draft:** write, build, and test in the order's own worktree at `../<repo>.st/WO-…/`. No commits.
- **L2, stage:** L1, plus commits on the order's branch `st/WO-…`, and a push if you approve `--push`.
- **L3:** merges, releases, deploys, and secrets. Always yours; no agent ever holds it.

**Taking the work.** An order's workspace is a git worktree on its own branch.
- **L2 work** arrives as commits: review them with `git log -p main..st/WO-…`, then `git merge st/WO-…`.
- **L1 work** arrives as uncommitted files in `../<repo>.st/WO-…/`: review them with `git -C ../<repo>.st/WO-… diff` and `git -C ../<repo>.st/WO-… status`, commit them there yourself, then merge the branch.
- **Afterwards:** `st prune` removes finished worktrees and merged or rejected branches.

**Decisions.** When you settle a question, the copilot hands you the line to sign:
- `st decide --title … --decision … [--dissent "copilot: …"]`.
- Every briefing from then on carries every decision in force. This is how the
  team's output stays uniformly designed.
- If the copilot argued and you overruled it, the dissent is signed into the
  record with the decision.

## 3. An existing project

### Add the team

```bash
cd ~/code/your-project
st init --default-standing     # creates .surgical-team/; L0 work needs no approval
git add .surgical-team && git commit -m "Add surgical team ledger"
st doctor
```

The ledger is the only thing added to the project. Teammates who don't use
`st` see a `.surgical-team/` directory and nothing else.

### Start a session

```bash
kiro-cli chat --agent st-copilot   # Kiro
agent "/st"                        # Cursor Agent CLI only
```

For Cursor, this supported and verified entry point is the Agent CLI only. Do
not run a team session in the Cursor IDE until it is verified: the IDE probe did
not route tool calls through user-level hooks, so the guard may be absent (see
the README's [Limits](README.md#limits-and-open-questions)). Only that Agent CLI
chat is the team. Every other Agent CLI chat in the project is ordinary Cursor,
which you can use for hands-on work.

Begin with "scrub in". The copilot reads `st status` and the last journal entry,
and briefs you in under a dozen lines. End with "scrub out", and it writes the
journal entry.

### First session: find out what you have

Start with L0 work. It changes nothing and needs no approval. Things to ask
the copilot:

- "Have the archaeologist characterize the billing module: entry points, side
  effects, what a rewrite must preserve." For legacy stacks, see
  [archaeologist](skills/archaeologist/SKILL.md).
- "Ask the Python language lawyer whether our async error handling is correct."
- "Get a security review of the last ten commits on main."

The copilot drafts each one as an order and dispatches it, then reads the
report back against the order's checks.

### Write down the conventions the code already follows

Ask the copilot to propose the project's standing design decisions from what it
found, such as error handling, layering, naming, and test style. Sign the ones
you agree with:

```bash
st decide --title "Errors" --decision "Domain errors are Result values; exceptions only at the edge"
```

From then on, every specialist's briefing carries them, so new work matches the
existing design.

### Make a change surgically

A reliable order of operations for changing existing code:

1. **Pin the current behavior.** Order a `tester` at L1 to write characterization
   tests from the spec or the observed behavior. Mark the implementation
   `blind`, so the tests come from the contract and not from the code.
2. **Make the change.** That's you, the surgeon, as in Brooks. Use your own
   editor, or an ordinary Cursor Agent CLI chat. A language lawyer can draft a
   patch at L1 when you want one.
3. **Review it independently.** Order a `reviewer` at L0 on the commit range.
   The order pins `inputs.review: {"base": …, "head": …}` to commit SHAs, so the
   review covers exactly what you approved. Add `security-reviewer`,
   `infra-reviewer`, or `accessibility-reviewer` when the change touches their
   area.
4. **Accept and merge.** Read the check line first, then the diff, then merge.

### Diagnose a problem

Export the evidence (logs, timelines, tickets, deploy records) into the
project, or somewhere the order names. Then ask the copilot for an
`incident-analyst` order:

```text
Checkout failed for 40 minutes last night. The log export is in incident/2026-10-13/.
Find the root cause.
```

The analyst grades its evidence, separates observation from inference, and
reports BLOCKED when it has no evidence, rather than inventing a cause. If it
needs a live read-only source, such as a log query, the order must grant it in
`inputs.sources`, and you approve that order yourself. See
[read-only sources](skills/surgical-team-protocol/references/authority-levels.md#read-only-sources).

### Cut down approvals for routine work

When you notice you are approving the same kind of order over and over, issue a
standing order:

```bash
st grant --role tester --max L1 --budget 30 --expires 2026-12-31 \
  --scope "Adding or extending tests for modules that already have tests"
```

Standing orders never grant pushes or L3. Keep per-order approval for L2 and
for anything that pushes.

## 4. A new project

Brooks' surgeon defines the specification and designs the program before
anyone builds. Start there.

### Create the repository with a first commit

```bash
mkdir ~/code/new-thing && cd ~/code/new-thing
git init -b main
$EDITOR SPEC.md                  # what it does, for whom, and what it must never do
git add SPEC.md && git commit -m "Initial spec"
st init --default-standing
git add .surgical-team && git commit -m "Add surgical team ledger"
```

The first commit matters: each order's workspace branches from it.

### Shape the spec with the copilot

Start a session (`kiro-cli chat --agent st-copilot`, or `agent "/st"` in the
Cursor Agent CLI) and work
the spec through with it. Its job is to argue: what's missing, what conflicts,
and what forecloses later options. Ask for an option paper when there's a real
choice ("three ways to store sessions, with trade-offs"). That's L0, so it's free.

Keep `SPEC.md` yours. The copilot can propose wording; the editor can finish the
prose once the substance is settled.

### Make the founding decisions

Decide the things every later order must respect, and sign each one: language
and runtime, architecture and layering, error handling, data model, testing
strategy, and dependency policy.

```bash
st decide --title "Runtime" --decision "TypeScript on Node 22, ESM only" \
  --rejected "Deno: team unfamiliar" --dissent "copilot: Bun would halve CI time"
```

These are the project's conceptual integrity in writing. Every briefing carries
them.

### Build the workbench

Order the `toolsmith` to set up the development environment: the build, the
test runner, linters and formatters, and CI. Approve it at L2, so the work
arrives as commits you can review and merge.

### Build in small orders

For each slice of the spec:

1. **Tests from the spec.** Order a `tester` at L1 to write tests from
   `SPEC.md` (`inputs.files`) before the implementation exists, or alongside it
   with the implementation `blind`.
2. **The code.** You write it. That's the surgeon's cut. A language lawyer can
   draft a minimal patch at L1 when you want a head start, and judges idiom and
   API design at L0.
3. **Review.** Order a `reviewer` on the range at L0.
4. **Docs.** Order the `editor` for READMEs, API docs, and ADRs, starting from
   your notes.
5. **Merge, then `st prune`.**

### Keep the team small

Spin up a specialist only when there is a need for one. The default standing
order makes L0 work free. Add standing orders for routine L1 work once a
pattern emerges.

## 5. Everyday commands

| You want to | Run |
|---|---|
| See the board | `st status` |
| Look at one order | `st show WO-…` |
| Approve, accept, reject | `st approve WO-…`, `st accept WO-a WO-b`, `st reject WO-c -m "why"` |
| Re-run an order's checks | `st check WO-…` |
| Recover a stuck order | `st reclaim WO-… --reason "…"` |
| Record a decision | `st decide --title … --decision …` |
| Clean up finished orders | `st prune --dry-run`, then `st prune` |
| Check the environment | `st doctor` |

## 6. Removing the team

```bash
st prune --force               # finished orders' worktrees and branches
git rm -r .surgical-team        # the ledger, from one project
st uninstall                    # agents, hooks, and /st, from your machine
```

Your trust root at `~/.config/surgical-team/` stays until you delete it by
hand.
