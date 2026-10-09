# Surgeon's Charter

You're the surgeon. Brooks' chief programmer personally defined the
functional and performance specifications, designed the program, coded it,
tested it, and wrote its documentation. With agents on the team, you still
own every one of those outcomes, but you no longer have to do the typing for
all of them.

The team exists to keep you working on the parts that require judgment.

## Setup, once

```bash
export PATH="/path/to/the-surgical-team/bin:$PATH"
st setup --key ~/.ssh/id_ed25519 --identity you@example.com  # your signing key
st install                                                   # writes ~/.kiro/agents/st-*.json
```

Then, in each project:

```bash
st init --default-standing   # creates .surgical-team/; L0 work needs no approval
git add .surgical-team && git commit -m "Add surgical team ledger"
kiro-cli chat --agent st-copilot
```

Your signing key is the team's trust root. Every approval, verdict,
decision, and standing order is signed with it, and agents cannot produce a
signature, so nothing an agent writes can grant authority. That holds only
if the key cannot sign without you, so `st setup` refuses a key with no
passphrase. Use one of:

- a key with a passphrase (you type it when you sign),
- a hardware key (`ssh-keygen -t ed25519-sk`; you touch it when you sign), or
- a key in `ssh-agent` added with `ssh-add -c` (you confirm each use), passing
  the `.pub` path to `st setup`.

Why it matters: the guard stops agents from running `ssh-keygen` or the
signing commands, but code an agent runs inside its workspace (a build, a
test, a script it wrote) is not parsed. A key that signs silently could be
used by that code.

## What only you do

These commands sign with your key. Run them in your own terminal; the guard
blocks them for every agent.

| You | Command |
|---|---|
| **Approve** an order, choosing how far it may reach and for how long | `st approve WO-… [--level L0/L1/L2] [--push] [--for MINUTES]` |
| **Accept, reject, or defer** reported work, several at once | `st accept WO-a WO-b`, `st reject WO-c -m "why"`, `st defer …` |
| **Decide**, so nobody has to re-ask | `st decide --title … --decision … [--supersedes DEC-…]` |
| **Grant** standing authority for routine work | `st grant --role tester --max L1 --budget 30 --scope "…" --expires …` |
| **Revoke** a decision or standing order | `st revoke DEC-…` |
| **Cancel** an order | `st cancel WO-…` |

And beyond the commands:

1. **Hold conceptual integrity.** You keep the whole design in mind. If an
   agent's output doesn't fit it, reject the output, even when it works.
2. **Merge.** Nothing reaches the mainline, deploys, or gets published
   except by you. That's L3, and no agent ever holds it.

## What you delegate

Pretty much everything else: exploration, drafting, test design, tooling,
documentation, language-specific review, and status. Bookkeeping is
delegated to `st`, not to an agent.

## Working with the copilot

You talk to the copilot; it dispatches the rest of the team.

| You say | What happens |
|---|---|
| "Scrub in." | The copilot briefs you from `st status` and the last journal. |
| Describe a problem or idea | The copilot works it with you, challenges it, and brings options. |
| "Write that up as an order." | The copilot files it with `st draft` and hands you the `st approve` line. |
| *(you run `st approve …`)* | The copilot dispatches it to a guarded `st-<role>` subagent. |
| "Status." | `st status`. |
| Report comes back | The copilot runs `st check`, compares claims to checks, and hands you the verdict line. |
| "Decision: …" | The copilot hands you the `st decide` command. |
| "Scrub out." | The copilot writes the journal with `st journal`. |

## Keeping the throughput up

The design puts you in the loop deliberately, which makes you the
bottleneck. Approval fatigue leads to rubber-stamping, which is worse than
no approval. So spend your attention where the risk is:

- **L0 is pre-approved** by the default standing order. Reviews and option
  papers dispatch without asking you.
- **Grant standing orders for routine L1 work** (tests for modules that
  already have tests, doc fixes). Standing orders never grant pushes or L3.
- **Approve per order** for L2 and for anything with a push. That is where
  your attention pays.
- **Batch verdicts.** `st accept` takes several IDs.
- **Read the check line first.** The board shows `checks 3/3 pass` or
  `checks NOT RUN` next to each report. A report whose checks contradict it
  needs your attention; a report whose checks pass and whose diff you have
  read needs one command.

## Your obligations to the team

- **Write down intent.** Agents can't read your mind, and they don't
  remember across sessions. One clear sentence of intent saves rework.
- **Give verdicts.** Unreviewed reports pile up and the team stalls.
- **Don't route around the ledger.** If you change something by hand, tell
  the copilot so it lands in the journal.
- **Keep the team small.** Spin up a specialist only when there's a need.

## Brooks' warning, applied

The structure only works because the problem is never divided: the surgeon
and the copilot are both cognizant of all of the design and all of the code.
An agent's understanding does not survive the session, so in practice that
means you.

Delegating typing is fine. Delegating understanding isn't. If you accept
code you don't understand, you've stopped being the surgeon and become a
rubber stamp. Ask the copilot or the language lawyer to walk you through it
until you do understand it, or reject it.
