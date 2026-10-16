# General Change Review Procedure

This is the deep procedure behind the ordered passes in
[the reviewer skill](../SKILL.md). The target is immutable: use the `base` and
`head` SHAs in the dispatch briefing, never a branch name that can move.

A review is an argument from evidence. The diff says what changed; the files at
`head` say what will exist; the order and active decisions say what was intended.
None is sufficient alone.

## Pass 1: establish the review frame

Before opening the diff, write five short statements:

1. The user-visible or system-visible behavior the order intends to change.
2. Behavior explicitly held constant.
3. Paths and systems declared in and out of scope.
4. Acceptance criteria, preserving their exact qualifiers.
5. Constraints from each inlined active `DEC-` record.

These statements are not a redesign. They prevent the implementation from
quietly becoming the specification.

A conflict between the order and an active decision is a blocker: report it and
ask the surgeon which authority changes. Do not resolve the conflict by choosing
the newer-looking text. An ambiguity that does not prevent concrete review goes
under `Unverified` or becomes an open question; it is not automatically a
finding against the change.

**WRONG:** the order says existing callers remain compatible, while the change
removes a required response field. Minimal fix: restore the field or obtain a
surgeon decision changing the compatibility requirement.

**TASTE:** the commit message calls a component a service while the decision
calls it a worker, with no behavioral consequence. Note only if it causes real
ambiguity; otherwise omit it.

## Pass 2: read the commit series

Use the exact `git log <base>..<head>` command from the briefing. Commit order can
reveal intent that a squashed diff hides, but commit messages are claims, not
authority.

For each commit, note:

- concern and touched subsystem;
- whether it is implementation, test, generated output, migration, config, CI,
  dependency, or cleanup;
- claims such as “no behavior change,” “backward compatible,” or “regenerate”;
- fixup/revert patterns that suggest an invariant was repaired incompletely;
- commits whose purpose does not map to the signed order.

Do not review commit style. A messy series is not a defect if the head tree is
sound. It matters only when intermediate commits will be shipped separately or
the order requires a bisectable series.

**UNIDIOMATIC:** a dependency bump is mixed into an unrelated fix and changes the
resolved graph, increasing rollback and diagnosis cost. Minimal fix: remove it
from this change or explain why it is required.

## Pass 3: inventory the whole diff

Read `git diff <base>...<head>` in full. Three-dot form compares `head` with the
merge base of `base` and `head`; use the command supplied by the briefing rather
than substituting two-dot form.

Build a file inventory. For every path, assign one reason tied to intent:

| Kind | Questions |
|---|---|
| Production code | Which behavior and callers change? |
| Tests/fixtures | Which changed behavior would make them fail at base? |
| Schema/migration | Is rollout and rollback order safe for mixed versions? |
| Config/feature flag | What is the default, and who supplies each environment value? |
| CI/build | Does the gate run on the intended events and artifacts? |
| Manifest/lockfile | Is the direct change intended; what transitive graph changed? |
| Generated file | Does it correspond exactly to a source change? |
| Documentation | Does it describe behavior that actually exists at head? |

Watch for binary files, permission changes, renames with edits, submodule SHAs,
large generated churn, and lockfiles. They are easy to skip and often carry the
operational effect.

Unexplained scope is not automatically wrong. Ask whether it is necessary. It is
**WRONG** when it violates `scope.out`, an active decision, or a compatibility
promise; **UNIDIOMATIC** when it merely couples unrelated risk with a named cost.

## Pass 4: read touched files at head

A hunk has too little context. Read every touched text file as it exists at
`head`, then follow only the callers and definitions needed to test the hunk's
assumptions.

For each changed unit, identify:

1. Inputs and who controls them.
2. Preconditions and where they are enforced.
3. State read and state written.
4. Success value and every failure path.
5. Cleanup or rollback obligations.
6. Callers that rely on the old behavior.
7. Concurrency, retry, ordering, and time assumptions.
8. Public or persisted representations that outlive the process.

Read declarations and configuration, not only implementation. A harmless-looking
call can be wrong because a default changed elsewhere. Read both sides of a
renamed field, event, feature, and serialization boundary.

Every finding names a surviving `head` location. For an erroneous deletion,
anchor the finding at the caller, schema, dispatch table, or configuration whose
head behavior is now incomplete. If no surviving line exists, name the `head`
path and symbol plus the diff hunk, not only a line from `base`.

Do not report speculative cascades separately. One root cause with all material
consequences is easier to fix than five findings about its symptoms.

## Pass 5: test adequacy

Read the relevant tests at `head`; do not run them at L0. Map each material claim
to a test or to `Unverified`.

A useful regression test has three properties:

- it exercises behavior changed by the diff;
- it would fail against `base` for the intended reason;
- it observes a contract or outcome, not merely that a mock received the values
  the implementation itself constructed.

Check normal, boundary, malformed-input, dependency-failure, retry, partial
success, and compatibility cases when the implementation exposes them. Do not
demand every category mechanically.

**WRONG:** an acceptance criterion explicitly requires a regression test, but
only production code changed. Minimal fix: hand a test order to `tester` that
names the behavior and failure at base.

**UNIDIOMATIC:** a retry-state change has only a happy-path test, leaving a
specific duplicate-side-effect regression unguarded. Minimal fix: ask `tester`
for a test that injects a post-side-effect timeout and asserts one durable effect.

**TASTE:** table-driven versus separate test functions when both expose failures
clearly. Do not report it.

Never claim a test passes. Use “present and appears to exercise” for static
review, and put the run under `Unverified`.

## Pass 6: classify and size findings

Before filing a candidate, answer:

1. What exact behavior fails or what concrete cost is introduced?
2. Which input, state, ordering, or deployment condition triggers it?
3. What repository evidence establishes that condition is reachable?
4. Which signed requirement, decision, code contract, or versioned authority
   makes it wrong?
5. What is the smallest fix or surgeon question?

If answer 3 or 4 is absent, it is not yet a finding. Put the hypothesis under
`Unverified` and state the read, test, or external evidence needed.

Size by root cause:

- One finding per independently fixable defect.
- Combine multiple locations when one invariant is broken in the same way.
- Split findings when fixes can be accepted independently or have different
  obligations.
- Mention consequences in one finding rather than filing each consequence.
- Omit compliments, summaries of the diff, and style observations from findings.

Labels describe obligation, not severity. A tiny off-by-one can be **WRONG**; a
large refactor preference can be **TASTE**.

## What blocks and what does not

A review verdict is **unsound** when at least one established **WRONG** finding
makes the stated behavior unsafe, incorrect, non-compliant, or incompatible.
“Sound with required fixes” means the change can become sound through bounded,
identified fixes. “Sound” permits `UNIDIOMATIC` and `TASTE` observations, though
only useful ones should remain.

Block the review itself when:

- the briefing lacks immutable base or head SHAs;
- the commits or required paths cannot be read;
- intent conflicts with an active decision and the conflict controls the result;
- an acceptance criterion requires an external fact but no signed read-only
  source or supplied export exists;
- a guard block removes evidence essential to the verdict.

Do not block merely because:

- tests cannot run at L0; mark the run unverified;
- a preferred refactor is absent;
- unrelated code may contain defects;
- commit messages are poor;
- the change is larger than preferred but still reviewable.

When the review exceeds the order's budget, report `PARTIAL`: list paths and
passes completed, paths not reviewed, and why no full verdict is justified.

## Review-report pitfalls

**Invented reachability. WRONG review practice.** A possible nil value is not a
finding until a caller or input can produce it. Fix the review by citing that
path or moving the claim to `Unverified`.

**Diff-only certainty. WRONG review practice.** A hunk may be protected by a
caller or contradicted by configuration. Fix: read the whole file at `head` and
the minimum surrounding graph.

**Finding inflation. UNIDIOMATIC review practice.** Five comments on one missing
validation obscure the root cause. Fix: one finding, all affected locations,
one minimal repair.

**Solution takeover. UNIDIOMATIC review practice.** A broad redesign replaces a
small correctness fix. Fix: show the smallest repair and hand design choices to
the surgeon.

**Polished speculation. WRONG review practice.** Generated prose can make an
unverified concern sound observed. Fix: require a head location, reachability
evidence, authority, and a trigger for every finding.
