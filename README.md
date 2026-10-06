# The Surgical Team

A proof-of-concept agent team modeled on Harlan Mills' *chief programmer team*,
as described by Frederick P. Brooks Jr. in "The Surgical Team" (chapter 3 of
*The Mythical Man-Month*, 1975).

The surgeon is a human. Everyone else on the team is an agent.

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
hands without diluting the mind.

## Role mapping

| Brooks (1975) | This system | Kind | Skill |
|---|---|---|---|
| Surgeon (chief programmer) | The user | Human | [SURGEON.md](SURGEON.md) |
| Copilot | Design partner, critic, context keeper, primary session agent | Agent | [copilot](skills/copilot/SKILL.md) |
| Administrator (+ secretary) | Dispatcher, budgets, workspaces, status, outward correspondence | Agent | [administrator](skills/administrator/SKILL.md) |
| Editor (+ secretary) | Turns surgeon drafts into finished docs; handles publishing mechanics | Agent | [editor](skills/editor/SKILL.md) |
| Program clerk | Keeper of the ledger: orders, reports, decisions, status | Agent | [program-clerk](skills/program-clerk/SKILL.md) |
| Toolsmith | Dev environment, scripts, CI, MCP servers, tools for the other agents | Agent | [toolsmith](skills/toolsmith/SKILL.md) |
| Tester | Adversary from the spec, plus scaffolding and test data for daily work | Agent | [tester](skills/tester/SKILL.md) |
| Language lawyer | Interchangeable language specialist (Rust first) | Agent | [language-lawyer-rust](skills/language-lawyer-rust/SKILL.md) |
| *(new)* | Shared rules every agent follows | Protocol | [surgical-team-protocol](skills/surgical-team-protocol/SKILL.md) |

### What changed from 1975

- **Secretaries are merged into their principals.** The administrator handles
  correspondence (tickets, PR descriptions, status notes), and the editor
  handles production mechanics.
- **The copilot is the front channel.** Brooks' copilot "knows all the code
  intimately," so it's the natural agent to hold session context. It's the
  agent the surgeon talks to.
- **The administrator dispatches.** Brooks' administrator managed money,
  people, space, and machines. Here those become token and time budgets, agent
  instances, worktrees and branches, and compute.
- **The program clerk keeps its importance.** Mills considered the clerk
  critical, on the grounds that recording the work is what moves programming
  from private art toward public practice. Agents forget between sessions, so
  the clerk's ledger serves as the team's long-term memory.
- **Agents may write code; only the surgeon accepts it.** Brooks let the
  copilot write code without being responsible for any of it. That principle
  now covers every agent. Agents produce drafts on branches or in worktrees,
  and nothing reaches the mainline until the surgeon accepts it.
- **The language lawyer is a slot, not a person.** Brooks noted that one
  language lawyer can serve two or three surgeons. Here, any
  `language-lawyer-<lang>` skill that satisfies the
  [language lawyer contract](skills/surgical-team-protocol/references/language-lawyer-contract.md)
  can fill the slot. Rust is the first one.

## Architecture

```
                         ┌──────────────┐
                         │   SURGEON    │  human: decides, designs, accepts
                         └──────┬───────┘
                                │ conversation
                         ┌──────▼───────┐
                         │   COPILOT    │  primary session agent; drafts work orders
                         └──────┬───────┘
                                │ approved work orders
                         ┌──────▼───────┐
                         │ADMINISTRATOR │  dispatch, budgets, worktrees, status
                         └──────┬───────┘
          ┌──────────┬──────────┼──────────┬──────────────┐
     ┌────▼───┐ ┌────▼────┐ ┌───▼───┐ ┌────▼─────┐ ┌──────▼───────┐
     │ TESTER │ │TOOLSMITH│ │EDITOR │ │ LANGUAGE │ │ (future      │
     │        │ │         │ │       │ │ LAWYER   │ │  specialists)│
     └────┬───┘ └────┬────┘ └───┬───┘ └────┬─────┘ └──────────────┘
          └──────────┴──── reports ────────┘
                                │
                         ┌──────▼───────┐
                         │PROGRAM CLERK │  ledger: .surgical-team/
                         └──────────────┘
```

Every interaction between agents is a **work order** with a matching
**report** (see the [protocol](skills/surgical-team-protocol/SKILL.md)). The
clerk files every order, report, and surgeon decision under `.surgical-team/`
in the target project. That gives a cold-started agent, or a human
teammate, enough to reconstruct the state of the work.

## Repository layout

```
the-surgical-team/
├── README.md                     # this file
├── SURGEON.md                    # charter for the human in the chair
├── scripts/validate-skills.sh    # validates all skills against the Agent Skills spec
└── skills/
    ├── surgical-team-protocol/   # shared rules: authority, work orders, reports, ledger
    │   ├── references/           # authority levels, ledger layout, language-lawyer contract
    │   └── assets/               # work-order, report, decision, language-lawyer templates
    ├── copilot/
    ├── administrator/
    ├── editor/
    ├── program-clerk/
    ├── toolsmith/
    ├── tester/
    └── language-lawyer-rust/
        └── references/           # ownership and soundness, API design, toolchain, pitfalls
```

Each directory under `skills/` is a standalone [Agent Skill](https://agentskills.io/specification):
a `SKILL.md` with YAML frontmatter, plus optional `references/` and `assets/`
loaded through progressive disclosure.

## Using it (Kiro CLI)

Kiro discovers skills through `skill://` resources. To try the team in a
project, either symlink the skills into the project's `.kiro/skills/`
directory:

```bash
mkdir -p .kiro/skills
for s in /Users/cbales/Sandbox/the-surgical-team/skills/*/; do
  ln -s "$s" ".kiro/skills/$(basename "$s")"
done
```

or reference them from a custom agent config:

```json
{
  "name": "operating-room",
  "description": "Copilot for a human surgeon; dispatches the surgical team",
  "resources": [
    "skill:///Users/cbales/Sandbox/the-surgical-team/skills/*/SKILL.md"
  ]
}
```

Then start a session and tell the copilot to scrub in. The intended flow is
described in [SURGEON.md](SURGEON.md).

## Validation

```bash
scripts/validate-skills.sh
```

This script runs the reference validator (`skills-ref`) on every skill.

## Status and open questions

This is a v0.1 specification set. It has no runtime of its own yet; it relies
on the host agent (Kiro, or any client that supports skills and sub-agents) to
spawn roles. Questions for future iterations:

- Should each role become its own agent config (tool permissions per role),
  or remain skills loaded into generic sub-agents?
- Should the copilot have standing authority to dispatch low-risk orders
  (L0/L1) without asking the surgeon each time? The protocol supports
  standing orders, but no role ships with one; the surgeon grants them
  per project. (The program clerk's ledger-write exception is part of the
  protocol itself, not a standing order.)
- How should the system scale to multiple surgeons? Brooks' answer was a
  system architect above the surgeons, and shared language lawyers and
  administrators.
- What other specialists belong on the team? Candidates: security reviewer,
  performance analyst, UX reviewer, and other language lawyers (TypeScript,
  Python, Go).

## Sources

- Brooks, F. P. Jr. *The Mythical Man-Month*, ch. 3 "The Surgical Team."
  Addison-Wesley, 1975; anniversary ed. 1995.
- Mills, H. "Chief programmer teams: principles and procedures." IBM Federal
  Systems Division Report FSC 71-5108, 1971.
- Agent Skills specification: <https://agentskills.io/specification>
