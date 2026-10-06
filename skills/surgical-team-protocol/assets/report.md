# Report — WO-YYYYMMDD-NNN

Order       WO-YYYYMMDD-NNN
Role        <role that executed>
Authority   <level actually used>
Status      <DONE | PARTIAL | BLOCKED | DECLINED>
Completed   <ISO 8601 UTC>

## Summary
<Two or three sentences, outcome first. The surgeon may read only this.>

## Criteria
| # | Criterion | Met | Evidence |
|---|---|---|---|
| 1 | <restated> | yes/no | <command, file, or line reference> |
| 2 | <restated> | yes/no | <…> |

## Evidence
<Commands run and their actual output, trimmed to what matters. Files
created or modified, with paths. Test and lint results. If a claim here was
not verified by running something, say so explicitly.>

```
$ <command>
<output>
```

Files changed:
- `<path>` — <what changed>

## Workspace
<Branch, worktree, or scratch path where the work lives. For L2, the draft
PR number.>

## Cost
Wall clock  <actual> of <budgeted>
Tokens      <approximate> of <budgeted>

## Risks
<What could go wrong with this work in production or review. Be specific.
"None identified" is acceptable only if you actually looked.>

## Recommended
<What the surgeon should decide or do next. If you disagree with the order
itself, say it here, once, clearly.>

## Out of scope
<Things noticed but deliberately not touched, each with a suggested role and
a one-line order sketch. This is how the team surfaces work without
freelancing.>

- <finding> → suggest order for `<role>`: <one line>

## Blocker
<Only for BLOCKED or DECLINED. What stopped the work, and precisely what
would unblock it: a decision, an authority grant, a credential, a revised
order.>

---

## Verdict
<Appended by the program clerk once the surgeon rules.>
<accepted | rejected | deferred> — <ISO 8601 UTC>
<Surgeon's note, and any follow-up order IDs.>
