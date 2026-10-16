# Common Change Defects

Use this catalog after reading intent and the complete diff. It supplies prompts,
not findings. A pattern earns a label only when the pinned `head` and its callers
establish the trigger and consequence.

Each entry gives the usual label and smallest useful repair. Project contracts
can change a label: a deliberate, documented trade-off may be sound; a signed
criterion can make an otherwise advisory gap mandatory.

## Boundaries and representation

**Off-by-one range. WRONG.** Inclusive business limits become exclusive language
ranges, the final item is skipped, or `<= length` indexes one past the end.
Check empty, one-item, exact-page, and maximum-size inputs. Fix by naming the
boundary (`end_exclusive`, `max_inclusive`) and deriving the comparison once.

**Null, nil, or undefined crosses a boundary. WRONG.** A new optional field is
read as required, a missing map key becomes a zero value, or nullability is lost
in serialization. Trace the absent case from decoder to use. Fix with explicit
validation or a typed optional value and a defined default.

**Falsy is confused with absent. WRONG.** `0`, `false`, or an empty string is
replaced by a default intended only for absence. Fix with a null/undefined check
rather than truthiness.

**Unit or encoding mismatch. WRONG.** Seconds are treated as milliseconds, bytes
as characters, decimal money as binary floating point, or an encoded identifier
is decoded twice. Fix with a type or name carrying the unit and one conversion at
the boundary.

**Narrowing or overflow. WRONG.** A count, offset, timestamp, or size is cast into
a smaller or signed representation without a proven bound. Fix with checked
conversion and an explicit out-of-range error.

## Errors and partial work

**Error swallowed as success. WRONG.** An exception is logged and ignored, a
rejected promise is converted to an empty result, or a failed write returns a
success status. Fix by propagating a typed failure or returning an explicit
partial-result contract.

**Catch is wider than recovery. WRONG.** A broad catch intended for “not found”
also catches network, permission, parse, and programming failures. Fix by
matching only the recoverable condition and rethrowing the rest.

**Cleanup masks the primary error. WRONG.** A close, rollback, or telemetry
failure replaces the operation's real failure. Fix by preserving the primary
error and attaching cleanup failure as secondary context.

**Partial failure is presented as atomic success. WRONG.** A multi-item operation
commits some effects, fails later, and reports only a generic error; retry then
duplicates completed effects. Fix with a transaction, compensating operation, or
per-item durable status and an idempotency contract.

**Rollback assumes the old binary. WRONG.** A migration or config change is
compatible only with the new code, so rollback cannot read new state. Fix with an
expand/migrate/contract sequence or a documented no-rollback surgeon decision.

**Resource released only on success. WRONG.** A file, lock, transaction, stream,
temporary file, subscription, or goroutine/task leaks on an early return. Fix
with the language's scoped cleanup construct and test the failure path.

## Idempotency, retry, and concurrency

**Retry repeats an irreversible side effect. WRONG.** The timeout occurs after a
remote commit but before acknowledgment, and the next attempt creates a second
charge, message, or row. Fix with a stable idempotency key or reconciliation by a
unique operation identity.

**Retry without bounds or backoff. WRONG when failure can persist; otherwise
UNIDIOMATIC.** A tight loop amplifies an outage or rate limit. Fix with bounded
attempts, exponential delay, jitter, a total deadline, and clear terminal error.
Do not invent retry parameters; derive them from the dependency contract.

**Non-idempotent handler is attached to at-least-once delivery. WRONG.** Message
redelivery repeats effects because completion is not recorded atomically with
the effect. Fix with deduplication, an inbox/outbox pattern, or an idempotent
state transition.

**Check-then-act race. WRONG.** Code tests existence or permission, yields, then
acts on state that can change. Fix with one atomic operation, a transaction, a
lock covering both steps, or compare-and-swap.

**Lost update. WRONG.** Two workers read the same version and each writes a full
replacement; the later write erases the first. Fix with version preconditions,
atomic field updates, or serialized ownership.

**Lock scope crosses slow or reentrant work. WRONG when deadlock/starvation is
reachable; otherwise UNIDIOMATIC.** A lock is held through I/O, callbacks, or an
await. Fix by copying required state, releasing the lock, then doing external
work; revalidate before commit if needed.

**Cancellation leaves an intermediate state. WRONG.** Timeout or task
cancellation lands after a reservation but before its durable status update.
Fix with atomic state transitions, finally/defer cleanup, or a recoverable
pending state.

## Time, ordering, and pagination

**Local time is used as an instant. WRONG.** A date-time without zone is compared
across hosts or daylight-saving transitions. Fix by storing an instant in UTC
and carrying the presentation zone separately.

**Calendar duration becomes fixed seconds. WRONG.** “One month” or “next day” is
implemented as a constant duration. Fix with calendar arithmetic in the stated
time zone and explicit behavior at ambiguous or nonexistent local times.

**Clock type is wrong. WRONG.** Wall time measures a timeout and jumps when the
system clock adjusts, or monotonic time is persisted as an epoch. Fix: monotonic
for elapsed duration, wall-clock instant for externally meaningful timestamps.

**Sort order is partial or unstable. WRONG when pagination or selection depends
on it.** Rows ordered only by a non-unique timestamp move between pages. Fix with
a stable unique tie-breaker and use the same tuple in the cursor.

**Pagination termination guesses from page size. WRONG.** A short page is treated
as final despite a continuation token, or an empty page with a token terminates
early. Fix by following the API's explicit continuation contract.

**Cursor and filter drift. WRONG.** The next-page request omits a filter, tenant,
snapshot, or sort option from the first page. Fix by binding the cursor to all
query semantics or carrying the exact options forward.

**Offset pagination over mutable data. UNIDIOMATIC with a demonstrated duplicate
or omission risk; WRONG when stable traversal is promised.** Fix with keyset
pagination or a snapshot boundary.

## Configuration, migration, and dependencies

**Configuration default changes silently. WRONG.** A missing environment value
now enables behavior, widens access, or points at a production dependency. Fix
with an explicit default that preserves compatibility, validation at startup,
and documentation of the transition.

**Config is added in code but not deployment surfaces. WRONG.** Local examples
work while CI, manifests, or environment schemas omit the required value. Fix by
updating every active source of configuration or providing a safe default.

**Config drift through duplicate sources. UNIDIOMATIC.** The same setting exists
in two files with unclear precedence. Fix by choosing one source of truth or
making precedence executable and documented.

**Migration assumes one deployment order. WRONG.** New code reads a column before
it exists, old code cannot tolerate the new representation, or backfill races
writes. Fix with backward-compatible expansion, dual-read/write only when
necessary, backfill, verification, then contraction.

**Lockfile churn hides a graph change. WRONG when unexplained packages or major
versions enter the resolved graph; otherwise UNIDIOMATIC scope.** Fix by
regenerating with the intended package-manager version and isolating the direct
bump. Dependency vulnerability judgment belongs to `security-reviewer`.

**Generated output is stale. WRONG.** Source schema, client, fixture, or snapshot
changed without its generated counterpart, or generated output changed with no
source. Fix by regenerating at L1 through the declared toolchain and reviewing
the semantic delta.

**CI condition skips the protected case. WRONG.** A path or event filter means the
new test or build never runs for the change it protects. Fix the condition and
ask `toolsmith` to validate the pipeline wiring.

## Test defects visible in review

**Test asserts the mock. WRONG as evidence.** The test configures a mock to return
`x`, invokes a thin wrapper, and asserts `x`; it never observes the changed
mapping, persistence, or protocol. Fix by asserting the output or durable effect
at the production boundary.

**Test would pass at base. WRONG when offered as regression proof.** New assertions
exercise old behavior or are tautological. Fix by identifying the intended base
failure first, then making that outcome the assertion.

**Expected value is computed by the production algorithm. WRONG as evidence.**
The same defect appears on both sides. Fix with a hand-derived fixture, an
independent oracle, or an invariant/property.

**Time test sleeps. UNIDIOMATIC and often flaky.** Scheduler and host load become
part of correctness. Fix with an injected clock, event synchronization, or a
bounded eventually assertion tied to a real event.

**Shared mutable state leaks between tests. WRONG when order dependence is
reachable.** Fix with per-test isolation and cleanup that runs on failure.

**Random test cannot reproduce failure. UNIDIOMATIC.** Fix by recording and
reporting the seed and shrinking input where the framework supports it.

**Negative path is only a mocked exception. UNIDIOMATIC.** The adapter's actual
error shape, status, or transaction behavior remains untested. Hand the tester a
case at the nearest stable integration boundary.

## Characteristic of AI-generated changes

**Plausible but unused code. WRONG when the claimed behavior never reaches it.**
A helper, validator, middleware, or option is implemented but not registered,
called, exported, or wired. Fix by tracing from a real entry point and adding the
missing connection; remove dead scaffolding if no connection is intended.

**Parallel implementation bypasses the real path. WRONG.** Generated code creates
a second abstraction while callers continue using the first. Fix the existing
path or migrate callers explicitly; do not count an unused class as delivery.

**Hallucinated API or option. WRONG.** A believable method, config key, command,
or response field does not exist in the pinned version. Fix by checking official
versioned documentation or repository definitions; never “correct” it with
another remembered name.

**Happy-path completeness. WRONG when errors become false success.** The code has
polished types and comments but no cleanup, timeout, cancellation, duplicate, or
partial-failure behavior. Fix only the reachable failure paths established by
the touched boundary.

**Comment restates code while invariant is absent. UNIDIOMATIC.** Generated
comments narrate assignments but omit why ordering, locking, or validation is
safe. Fix by deleting narration and documenting the non-obvious contract.

**Defensive fallback erases evidence. WRONG.** Broad catches, empty collections,
or default objects make tests green while hiding dependency failure. Fix by
propagating failure or representing partial/unavailable state explicitly.

**Mock-shaped production API. UNIDIOMATIC.** Public seams mirror test doubles
rather than domain boundaries, adding parameters used only by tests. Fix by
keeping dependency injection at a stable boundary and testing observable
behavior.

**Duplicated near-match logic. WRONG when cases diverge.** Two generated branches
look equivalent but one omits validation, authorization, cleanup, or a field.
Fix by sharing the invariant-bearing operation or making the intentional
difference explicit.

## How to use the catalog

For each match, cite the `head` location, reachable trigger, consequence, and
contract. If one is missing, record a hypothesis under `Unverified`, not a
finding. Hand language correctness to `language-lawyer-<lang>`, exploit depth to
`security-reviewer`, test construction to `tester`, and tool execution to
`toolsmith`.
