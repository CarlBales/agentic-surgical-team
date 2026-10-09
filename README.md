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
| Language lawyer | Interchangeable language specialist (Rust first) | Agent `st-language-lawyer-rust` | [language-lawyer-rust](skills/language-lawyer-rust/SKILL.md) |
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
  work anyway.) Correspondence, the secretaries' old job, is the copilot's.
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
                   │ subagent stages, one per dispatched order  │ .surgical-team/  │
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
├── README.md, SURGEON.md
├── bin/st                       # control plane, guard, and agent-config installer (Python stdlib)
├── tests/test_st.py             # unit tests: ledger, signing, checks, guard
├── tests/scenarios.py           # behavioral scenarios: real agents, assertions on state
├── docs/findings.md             # the v0.1 review and how each finding was resolved
├── scripts/validate-skills.sh   # Agent Skills structural validation
└── skills/
    ├── surgical-team-protocol/  # shared rules; references/ and JSON templates in assets/
    ├── copilot/
    ├── editor/
    ├── toolsmith/
    ├── tester/
    └── language-lawyer-rust/
```

## Using it (Kiro CLI)

Requires Python 3.10+, git, and OpenSSH 8.1+ (for `ssh-keygen -Y`).

```bash
export PATH="$PWD/bin:$PATH"
st setup --key ~/.ssh/id_ed25519 --identity you@example.com   # key must need a passphrase, touch, or confirm
st install                                                    # ~/.kiro/agents/st-{copilot,editor,toolsmith,tester,language-lawyer-rust}.json

cd ~/code/your-project
st init --default-standing
kiro-cli chat --agent st-copilot
```

Each `st-<role>` agent loads only the protocol and its own role skill, and
runs every tool call through `st guard --role <role>`. Don't load these
skills into a general-purpose agent: they assume the guard and the ledger
exist.

The full working flow is in [SURGEON.md](SURGEON.md).

## Verification

```bash
python3 -m unittest discover -s tests   # control plane and guard (no model calls)
scripts/validate-skills.sh              # skills against the Agent Skills spec
python3 tests/scenarios.py              # live agents via kiro-cli; spends tokens, takes minutes
```

The scenarios assert on what happened (ledger state, the filesystem), never
on what the model said: a tester told to edit the main checkout leaves it
clean, a tester with no spec reports `BLOCKED`, a blind tester finds the
spec violation it cannot see in the code, and the copilot cannot approve
its own order.

## Limits and open questions

- **Authority lives outside the repository.** The guard trusts only
  signatures and a local lease store, never the ledger's state, so a forged
  or rolled-back ledger, or one pulled from another clone, grants nothing.
  Approvals expire, and each one backs at most one reported attempt.
- **The guard is a parser, not a sandbox.** It confines where agents write
  and what they run outside a workspace, but a build script run inside a
  workspace can do anything the user can. For hostile code, run the team in
  a container with the main checkout read-only. See
  [authority levels](skills/surgical-team-protocol/references/authority-levels.md).
- **Budgets are estimates.** Nothing in the team can interrupt a running
  subagent; hard limits come from the host. `st` records actual wall clock
  and flags overruns and stale dispatches.
- **Kiro only, for now.** The guard speaks Kiro's preToolUse hook format.
  Other hosts with pre-tool hooks need an adapter.
- **The scenario suite is small.** Five scenarios cover the authority
  boundaries and two role behaviors. They are pass/fail on single runs, and
  model behavior varies: run them several times before trusting a change to
  a prompt, and add a scenario whenever a role misbehaves.
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
