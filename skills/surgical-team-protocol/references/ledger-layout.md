# Ledger Layout

Mills considered the clerk's records critical: recording the work is what
moves programming from private art toward public practice. Agents forget
everything between sessions, so the ledger is the team's memory.

In v0.1 an LLM clerk kept it. Since v0.2 `st` does, because IDs, state, and
validation are functions, and a nondeterministic clerk can corrupt the only
durable memory the team has.

## Location and ownership

The ledger lives at `.surgical-team/` in the **main checkout** of the target
project and is committed with it. Worktrees live outside the repository at
`../<repo>.st/<WO-ID>/`, so recursive tools never see duplicate sources, and
`st` resolves the main checkout from any worktree, so the ledger is always
the live one and never a stale copy on a branch.

`st` is the only writer. The guard blocks every agent write to
`.surgical-team/`, wherever it appears.

The ledger is a record, not a source of authority. It is shared, so its
contents can come from anyone. Live authority is kept in an append-only
**lease store** at `~/.config/surgical-team/leases/<repo-hash>.jsonl` on the
surgeon's machine. `st dispatch` writes an `open` event and `st report`,
`reclaim`, `cancel`, and verdicts write `close` events. An order that the
ledger shows as `dispatched` with no live lease on this machine is labelled
`NO LIVE LEASE HERE` on the board and has no authority.

## Format and schemas

Every record carries `"format": 1`, and `format.json` holds the ledger's
format. The JSON Schemas for each record, the order spec, the report, signed
payloads, and lease events are in the team repository's `schema/` directory;
they are the contract any implementation of `st` must honor. `st draft`
refuses unknown spec fields, so a misspelled `blind` is an error, not a
silently dropped constraint.

`st` reads older formats but writes only the current one: on an older
ledger, writes stop with `run: st migrate` (surgeon-only; `--dry-run`
shows the changes). Migration never edits a spec, so approvals stay valid.
A ledger in a format newer than the installed `st` understands is refused,
and the guard grants no authority from it.

## Structure

```
.surgical-team/
├── format.json            # on-disk format version (`st migrate` upgrades)
├── STATUS.md              # generated board; never edited
├── events.jsonl           # append-only event log
├── orders/WO-….json       # spec, state, history, approval, dispatch
├── reports/WO-….aN.json   # one per attempt N
├── checks/WO-….aN.json    # harness runs of the executable criteria
├── verdicts/WO-….aN.json  # signed surgeon verdict
├── decisions/DEC-NNN.json # signed decisions, standing orders, revocations
├── journal/YYYY-MM-DD.md  # session journals (copilot writes via st journal)
└── .gitignore             # .lock, *.tmp
```

Records are append-only in spirit. A decision is never edited: a later
signed record supersedes or revokes it, and the original stays.

## Order states

```
drafted ──approve──▶ approved ──dispatch──▶ dispatched ──report──▶ reported
   ▲  └──(standing order)──dispatch──────────▲   │                  │
   │                                         │   │ reclaim          ├─accept──▶ accepted
   └──────────── revise (voids approval) ◀───┴───┘                  ├─reject──▶ rejected
                                                                    └─defer───▶ deferred
any non-terminal state ──cancel──▶ cancelled
```

| Transition | Who | Command |
|---|---|---|
| → drafted | copilot | `st draft`, `st revise` |
| drafted → approved | surgeon (signed) | `st approve [--level Ln] [--push]` |
| approved/drafted → dispatched | copilot | `st dispatch` (needs an unexpired approval or a standing order, an unconsumed grant, accepted dependencies, no path overlap; opens a lease) |
| dispatched → reported | the dispatched role | `st report` (needs the live lease; closes it) |
| dispatched → approved/drafted | copilot | `st reclaim --reason …` |
| reported/deferred → accepted/rejected/deferred | surgeon (signed) | `st accept`, `st reject`, `st defer` (batch: several IDs at once) |
| any → cancelled | surgeon (signed) | `st cancel` |

Every transition is recorded in the order's `history` and in `events.jsonl`.
Each dispatch increments `attempt`; reports, checks, and verdicts are per
attempt, so "exactly one report" means one per attempt.

## STATUS.md

Generated on every ledger change and by `st status`. Sections: integrity
problems (if any), awaiting the surgeon, blocked or declined, in flight
(with wall clock against budget, `OVER BUDGET`, `STALE`), ready to
dispatch, standing orders in force, recent decisions, live workspaces.
Because it is generated, it never conflicts in a way that matters: on a
merge conflict, take either side and run `st status`.

## Decisions

```bash
st decide --title "Retry belongs at the transport layer" \
  --decision "Retries live in the transport client, not at call sites." \
  --why "Call-site retries duplicated backoff in four places." \
  --consequence "Reviewers reject per-call-site retry loops" \
  --rejected "Shared helper at call sites: still invites drift" \
  --context WO-20260101-001 [--supersedes DEC-004]
```

Decisions are the most valuable records in the ledger: they stop the team
re-litigating settled questions. Keep them short. An order cites the ones
that bind it in `inputs.decisions`; `st` refuses citations of superseded,
revoked, expired, or unverifiable decisions, and the briefing inlines the
active ones.

## Session journal

`st journal` appends markdown from stdin to `journal/YYYY-MM-DD.md`. The
copilot writes it at scrub-out. It records what no other record does: the
reasoning that happened in conversation, open threads, and the first move
for next session.

## Hygiene

- **No secrets in the ledger.** It is committed. Reference credentials by
  name, never by value.
- **Timestamps are UTC**, ISO 8601, set by `st`.
- **`st verify`** checks every approval, verdict, cancellation, and
  decision signature. Run it after pulling a ledger someone else touched.
