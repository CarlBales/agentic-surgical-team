# Surgeon's Charter

You're the surgeon. Brooks' chief programmer personally defined the
functional and performance specifications, designed the program, coded it,
tested it, and wrote its documentation. With agents on the team, you still
own every one of those outcomes, but you no longer have to do the typing for
all of them.

The team exists to keep you working on the parts that require judgment.

## What only you do

1. **Decide.** Design choices, trade-offs, scope, and priorities. Agents
   surface options and argue for them, and you make the call. Each decision
   gets recorded as a `DEC-` entry so nobody has to re-ask.
2. **Hold conceptual integrity.** You keep the whole design in mind. If an
   agent's output doesn't fit it, reject the output, even when it works.
3. **Accept.** Nothing merges to the mainline, deploys, gets published, or
   gets announced without your explicit acceptance. That's authority level
   **L3** (see
   [authority levels](skills/surgical-team-protocol/references/authority-levels.md)).
   One step short of that is staging: an agent at L2 can commit to its own
   branch and, when the order says so, push it and open a draft PR. On a
   public remote that is a real disclosure, which is why you grant it per
   order rather than standing.
4. **Grant authority.** You decide how far each work order can go: read-only
   (L0), draft in isolation (L1), or stage on a branch (L2). You can issue
   standing orders that pre-approve routine work.

## What you delegate

Pretty much everything else. Exploration, drafting, test design, tooling,
documentation, language-specific review, bookkeeping, and status reporting
all go to the team. If you find yourself doing support work, it's worth
asking whether it should be a work order.

## Working with the copilot

You talk to the copilot, and the copilot talks to the rest of the team. A
typical session:

| You say | What happens |
|---|---|
| "Scrub in." | The copilot reads the ledger and briefs you on open orders, pending decisions, and what changed. |
| Describe a problem or idea | The copilot works through it with you, challenges it, proposes options, and asks what it needs to know. |
| "Write that up as an order." | The copilot drafts a work order with role, scope, acceptance criteria, authority, and budget. |
| "Approved." / "Approved at L1." | The administrator dispatches it. The clerk files it. |
| "Status." | The administrator reports from the status board. |
| "Accept WO-…" / "Reject WO-…: reason" | The clerk records your verdict. Accepted work moves forward (merge, publish) only under your authority. |
| "Decision: …" | The clerk files a `DEC-` record. Agents treat it as binding from then on. |
| "Standing order: …" | Pre-approves a class of work, for example "tester may run L1 orders under 30 minutes without asking." |
| "Scrub out." | The clerk writes the session journal and updates the status board. |

These are conventions, not syntax, so plain language works too. The copilot
should confirm what it understood whenever an instruction is ambiguous.

## Your obligations to the team

A surgical team works only if the surgeon does their part:

- **Write down intent.** Agents can't read your mind, and they won't remember
  across sessions unless the clerk records it. One clear sentence of intent
  saves a lot of rework.
- **Give verdicts.** Unreviewed reports pile up, and the team stalls behind
  them. Accept, reject, or defer them explicitly.
- **Don't route around the ledger.** If you make a change by hand, tell the
  copilot so the clerk can record it. Otherwise the team's picture of the work
  drifts from reality.
- **Keep the team small.** Brooks' point was that a few minds beat many. Spin
  up a specialist only when there's a real need.

## Brooks' warning, applied

The structure only works because the problem is never divided: the surgeon
and the copilot are both cognizant of all of the design and all of the code.

Delegating typing is fine. Delegating understanding isn't. If you accept code
you don't understand, you've stopped being the surgeon and become a rubber
stamp. When that happens, ask the copilot or the language lawyer to walk you
through the code until you do understand it, or reject it.
