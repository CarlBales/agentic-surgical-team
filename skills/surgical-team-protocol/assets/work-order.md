# WO-YYYYMMDD-NNN — <short title>

State       drafted
Role        <copilot | administrator | editor | program-clerk | toolsmith | tester | language-lawyer-rust>
Authority   <L0 | L1 | L2>
Issued      <ISO 8601 UTC>
Issued by   <administrator, on surgeon approval | standing order DEC-NNN>

## Intent
<One or two sentences: why this work matters to the surgeon. Not what to do —
why it is worth doing. The executing agent uses this to make small judgment
calls without asking.>

## Scope

In scope:
- <specific, bounded>

Out of scope:
- <the adjacent things the agent will be tempted to fix>

## Inputs
- Files: <paths>
- Decisions that apply: <DEC-NNN, DEC-NNN>
- Prior orders: <WO-…>
- Other context: <links, specs, issue numbers>

## Acceptance criteria
<Checkable conditions. Each one must be verifiable by a command, a file
state, or a reading. "Improve performance" is not a criterion; "p99 of
`bench_upload` under 200ms, measured by `cargo bench`" is.>

1. <criterion>
2. <criterion>

## Budget
Wall clock  <e.g. 30 minutes>
Tokens      <e.g. 60k>

## Workspace
<Required at L1 and above.>
- L1: `.surgical-team/scratch/WO-YYYYMMDD-NNN/` or worktree at <path>
- L2: branch `st/WO-YYYYMMDD-NNN-<slug>` from <base>

## Deadline
<optional>

## Notes
<Anything the agent should know but that is not a constraint. Known traps,
previous failed attempts, the surgeon's stated preference.>
