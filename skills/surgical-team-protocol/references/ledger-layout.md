# Ledger Layout

Mills considered the clerk's records critical: recording the work is what
moves programming from private art toward public practice. The clerk's
records were what let the whole team see the state of the work.

Agents forget everything between sessions. The ledger is the fix.

## Location and ownership

The ledger lives at `.surgical-team/` in the **target project**, not in this
specification repository. It is committed to the project's repository so that
history is shared and reviewable.

Every agent may read the ledger. **Only the program clerk writes the
records** — `STATUS.md`, `orders/`, `reports/`, `decisions/`, `journal/`.
The exception is `.surgical-team/scratch/<WO-ID>/`, which is gitignored
working space that L1 agents write for themselves and which is not part of
the record.

## Structure

```
.surgical-team/
├── STATUS.md                  # the board: one screen, always current
├── orders/
│   ├── WO-20260101-001.md
│   └── WO-20260101-002.md
├── reports/
│   ├── WO-20260101-001.report.md
│   └── WO-20260101-002.report.md
├── decisions/
│   ├── DEC-001.md
│   └── DEC-002.md
├── journal/
│   └── 2026-01-01.md          # one file per session
├── scratch/                   # gitignored; L1 workspaces
│   └── WO-20260101-002/
└── .gitignore                 # ignores scratch/
```

One file per order, report, and decision. Append-only in spirit: records are
superseded, never edited away. A decision that no longer holds gets
`Status: superseded by DEC-NNN`, and the original text stays.

## STATUS.md

The single file a cold-started agent reads first. Keep it under one screen.

```markdown
# Status — updated 2026-01-01T14:22Z

## Now
Reworking the upload retry path (DEC-007). Blocked on the surgeon's
verdict for WO-20260101-002.

## Open orders
| ID | Role | Auth | State | Budget used |
|---|---|---|---|---|
| WO-20260101-002 | tester | L1 | reported, awaiting verdict | 18m / 30m |
| WO-20260101-003 | language-lawyer-rust | L0 | dispatched | — |

## Awaiting the surgeon
- Verdict on WO-20260101-002 (report ready)
- Decision: retry backoff strategy — options in WO-20260101-001 report

## Standing orders in force
- DEC-014: tester may run L1 orders up to 30m without per-order approval

## Recent decisions
- DEC-007 Retry at the transport layer, not per call site (2026-01-01)
- DEC-006 Ship without resumable uploads in v1 (2025-12-28)

## Live branches
- st/WO-20260101-002-upload-retry-tests (draft PR #41)
```

## Order and report files

Order files use the [work order template](../assets/work-order.md) verbatim,
with a state line the clerk maintains:

```
State  drafted | approved | dispatched | reported | accepted | rejected | deferred | cancelled
```

The verdict on the report drives the state: `accepted`, `rejected`, or
`deferred`. A `deferred` order stays listed under "Awaiting the surgeon" in
`STATUS.md`, because the decision has not been made yet.

Report files use the [report template](../assets/report.md), plus the
surgeon's verdict appended once given:

```markdown
## Verdict
accepted — 2026-01-01T15:03Z
Merged as 4f2a1c9. Follow-up order WO-20260101-004 for the flaky timeout test.
```

A report with no verdict is the team's definition of a stall. Surface those
in STATUS.md under "Awaiting the surgeon."

## Decision records

Decisions are the most valuable thing in the ledger. They prevent the team
from re-litigating settled questions every session. Format:

```markdown
# DEC-007 — Retry belongs at the transport layer

Date      2026-01-01
Status    active            # active | superseded by DEC-NNN | revoked
Context   WO-20260101-001

## Decision
Retries live in the transport client, not at individual call sites.

## Why
Call-site retries were duplicating backoff logic in four places and made
the idempotency requirements invisible to readers.

## Consequences
- `UploadClient` owns backoff and jitter
- Call sites must not wrap uploads in their own retry loops
- Reviewers should reject per-call-site retry logic

## Alternatives rejected
- Per-call-site retry with a shared helper: still invites drift
- A retry middleware crate: more dependency than the problem warrants
```

Keep them short. A decision nobody reads is the same as no decision.

## Session journal

One file per session, written at scrub-out. It captures what no other record
does: the reasoning that happened in conversation.

```markdown
# 2026-01-01

Surgeon worked on upload reliability.

## Happened
- WO-20260101-001 (copilot, L0): surveyed retry options, three candidates
- DEC-007 recorded: retry at transport layer
- WO-20260101-002 (tester, L1): tests for the retry path, reported PARTIAL

## Open threads
- Timeout test is flaky under load; tester flagged it, not yet ordered
- Surgeon wants to revisit whether jitter should be configurable

## Notes for next session
Start with the verdict on WO-20260101-002.
```

## Bootstrapping

When `.surgical-team/` does not exist, the clerk creates it on the first
order, with `STATUS.md`, the five directories, and a `.gitignore` containing
`scratch/`. Numbering starts at `001` for both orders and decisions.

## Hygiene

- **No secrets in the ledger.** It is committed. Reference credentials by
  name, never by value.
- **Timestamps in UTC**, ISO 8601.
- **Cite IDs everywhere.** A report without an order ID is unfileable.
- **One screen for STATUS.md.** When it grows past that, the detail belongs
  in an order, a decision, or the journal.
- **Never rewrite history.** Supersede instead. The value of the ledger is
  that it records what the team actually believed at the time.
