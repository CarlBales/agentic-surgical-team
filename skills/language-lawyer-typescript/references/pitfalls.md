# TypeScript Pitfalls

Recurring findings, with emphasis on generated code. Each entry gives a
conditional judgment and the smallest honest fix. Use the baseline before
applying it: compiler options, module resolution, runtime, and library versions
change which patterns are valid.

## Characteristic of generated TypeScript

**Hallucinated APIs and types.** Plausible methods, props, package subpaths,
compiler options, lints, or exports do not exist in the pin. **WRONG.** Read
the installed declarations and versioned docs; a cast or ambient declaration
is not a repair.

**Version drift.** Code follows newer TypeScript, Node.js, React, or package
docs than the lockfile. **WRONG** when the feature is absent or different.
Use the pinned API or ask the surgeon to choose an upgrade.

**Invented object shapes.** A dependency response is reconstructed from
memory with missing union members or false required fields. **WRONG.** Import
its public type where appropriate, or validate into a narrow local shape.

**Assertions as repairs.** `as Expected`, `as unknown as Expected`, and `!`
replace diagnostics. **WRONG** for a reachable mismatch; **UNIDIOMATIC** when
a guard or model can express the invariant. Repair the source boundary.

**Redundant abstraction.** Locals all have annotations and simple functions
gain unused generics. Usually **UNIDIOMATIC**, sometimes **TASTE**. Keep
annotations where public contracts or intended widening need them.

**Fabricated verification.** Claiming `tsc`, ESLint, or tests passed without a
run is a protocol violation. At L0 say prediction; at L1 quote actual output.

## Promises and callbacks

**Floating promises.** An unawaited, unreturned promise loses completion and
failure. **WRONG** when the operation owns them. Await, return, or deliberately
detach with `void save().catch(reportError)`; `void save()` does not handle
rejection.

**`async` in `forEach`.** Callback promises are ignored. **WRONG** when
completion matters. Use `for...of` for sequential work or `Promise.all` over
`map` for deliberate concurrency.

**Async void callbacks.** A contextual `() => void` can accept an async
function whose promise the API ignores. **WRONG** when rejection is unowned.
Wrap and handle it; `@typescript-eslint/no-misused-promises` checks supported
cases.

**A `try` around an unawaited promise.** It cannot catch a later rejection.
**WRONG** when translating errors. Await inside the `try` or return a promise
with `.catch(...)`; elsewhere, `return await` can be a trade-off.

**Accidental serialization or fan-out.** Sequential awaits may be slow, while
unbounded `Promise.all` may overload a service. **TASTE** until ordering and
resource policy are known; **WRONG** when it violates that policy.

**Assumed cancellation.** Ignoring a promise need not stop its work. **WRONG**
when cleanup relies on that assumption. Use the API's documented abort
protocol.

## `any`, assertions, and narrowing

**`any` leakage from `JSON.parse`.** The standard declaration returns `any`,
which can flow through property access and inference without diagnostics.
**WRONG** when untrusted data is treated as validated. Assign to `unknown`,
validate, and expose only the validated type.

**Non-null assertions on lookups.** `map.get(key)!`, `array[index]!`,
`querySelector(...)!`, and `ref.current!` hide real absence. **WRONG** when
absence is possible. Check it, use a non-empty/stateful type, or establish the
invariant in a constructor. A comment does not make an unstable DOM or map
lookup present.

**Optional chaining as error suppression.** `account?.owner?.email` quietly
returns `undefined` even when missing `account` violates an invariant.
**WRONG** when absence should fail; use a guard with a meaningful error.
**UNIDIOMATIC** when callers now must chase an unnecessarily widened return.
It is correct for genuinely optional traversal.

**Truthiness loses valid data.** `value || fallback` replaces `0`, `false`,
and `""`; `if (index)` excludes index zero. **WRONG** when those are valid.
Use `??` for nullish defaulting or compare explicitly.

**A lying type predicate.** `isUser(value): value is User` checks one property
but promises ten. The checker trusts it. **WRONG.** Validate every promised
invariant or narrow the predicate's return type.

**Unchecked indexed access assumptions.** `rows[0].id` or `record[key].trim()`
can see `undefined` at runtime. **WRONG** when the collection may not contain
the entry. Enable and honor `noUncheckedIndexedAccess`, model non-empty data,
or check the read. Adding `!` preserves the bug.

**`Object.keys` cast to `(keyof T)[]`.** Runtime objects may have extra keys,
which is why the standard return is string-oriented rather than an exact
keyof list. The cast is **WRONG** when `T` is only a structural view of a
larger object. Keep runtime keys as strings and validate them, or operate on a
closed object created locally.

## Enums and state models

**Numeric enum values trusted from input.** Runtime input is not validated by
an enum annotation. **WRONG.** Check membership explicitly or decode into a
discriminated union. Remember that emitted numeric enums also have reverse
mappings; do not mistake `Object.values` for a list of only numeric members.

**`const enum` across package boundaries.** Consumers can inline values from a
different version than the runtime package, and some isolated transpilation
pipelines cannot process ambient const enums safely. **WRONG** when the
supported toolchain cannot preserve the version contract. Prefer a regular
enum or an `as const` object plus a value union after checking the baseline.
Inside one controlled build, the choice may be **TASTE**.

**Parallel optional fields instead of a union.** `{ loading?: boolean; data?:
T; error?: Error }` admits loading with stale data and an error. **UNIDIOMATIC**
when every consumer reconstructs the state machine; **WRONG** when code assumes
an impossible combination cannot occur. Use a discriminated union.

**Missing exhaustive handling.** A `switch` over a closed union silently
falls through after a new member is added. **WRONG** when every state requires
handling. Use a `never` exhaustiveness check or the verified
`@typescript-eslint/switch-exhaustiveness-check` rule.

## Modules and packages

**Barrel-file cycles.** An `index.ts` re-exports modules that import back
through the barrel. Types may appear fine while runtime initialization sees a
partially initialized binding or bundlers retain unintended modules.
**WRONG** when a value is read before initialization; otherwise
**UNIDIOMATIC** due to hidden dependency direction. Import siblings directly
inside the package and reserve the barrel for the external boundary.

**Type-only import used at runtime.** A symbol imported with `import type` is
erased. Constructing it, checking `instanceof`, or reading a static member is
**WRONG**. Use a value import when runtime identity is needed.

**Path aliases mistaken for output rewriting.** A tsconfig `paths` entry guides
TypeScript resolution; it does not by itself rewrite emitted import
specifiers. **WRONG** when Node.js receives an alias it cannot resolve. Ensure
the runtime, bundler, loader, or packaging step has the matching mapping.

**ESM syntax assumed to prove ESM output.** Compiler mode, file extension,
nearest package `type`, and host resolver all participate. **WRONG** when the
published entry loads under a different format. Establish the complete
baseline and make source, output, declarations, and exports map agree.

**CommonJS globals in ESM.** Using `require`, `module`, `exports`, or
`__dirname` in a true ESM file without a host-provided compatibility layer is
**WRONG**. Use the runtime's documented ESM facilities for the pinned version;
do not paste a workaround requiring a newer Node.js release.

**Deep import through package internals.** It may bypass the exports map and
bind callers to files the package does not promise. **WRONG** when the runtime
resolver blocks it; otherwise **UNIDIOMATIC** because upgrades can move it.
Use a documented public subpath.

**Declaration/runtime mismatch.** A `.d.ts` advertises a named export while
the selected JavaScript entry provides only a default or CommonJS object.
**WRONG.** Test the supported consumer modes and make conditional declarations
resolve with their runtime entries.

## Dates, equality, and JavaScript semantics

**Date strings without a clear zone.** ECMAScript's supported date-time string
format distinguishes date-only and date-time forms, and host display methods
apply local zones. Nonstandard strings are implementation-sensitive.
**WRONG** when business logic assumes another zone. Parse only a documented
format with an explicit offset or model a calendar date separately from an
instant. Do not assume a newer temporal API exists in the runtime.

**Local calendar arithmetic on instants.** Adding 24 hours is not always the
same as the next local day across offset transitions. **WRONG** when the domain
means a calendar day. Choose and document instant, local date/time, and time
zone semantics before selecting a library.

**Loose equality by habit.** `==` performs coercion and can equate values of
different types. **UNIDIOMATIC** in ordinary TypeScript; use `===`. The
intentional `value == null` check for both `null` and `undefined` is a known
idiom and not automatically a finding. It is **WRONG** only when coercion
changes the required result.

**Boolean sort comparators.** `items.sort((a, b) => a.rank > b.rank)` returns a
boolean, not a negative/zero/positive ordering. **WRONG.** Return an ordered
numeric comparison or explicit branches. Avoid subtraction when values are
not finite numbers.

**Assuming `readonly` freezes values.** TypeScript readonly modifiers are
compile-time, shallow restrictions. Aliases can still mutate and JavaScript
receives an ordinary object. **WRONG** when runtime immutability is a security
or correctness premise. Copy, encapsulate, or use a runtime freeze strategy
whose shallow/deep behavior is explicit.

## React and JSX

These are language-level closure and promise findings. Framework architecture,
render performance, and test strategy go to the matching specialist.

**Stale hook closures.** An effect, memo, or callback reads a value omitted
from its dependency list and therefore retains an older render's binding.
**WRONG** when behavior must follow the new value. Include the dependency or
restructure the effect; do not blindly suppress `react-hooks/exhaustive-deps`.
The exact rule behavior comes from the installed plugin version.

**Unstable dependencies recreated every render.** An object or function is
created outside an effect and then placed in its dependency list, causing the
effect to rerun each render. **UNIDIOMATIC** when the work can be moved inside
the effect or the primitive dependencies named directly. Memoization is not
a universal fix and can be **TASTE** when cost is unmeasured.

**Async effect callbacks.** An `async` effect callback returns a promise where
React expects no return or a cleanup function. **WRONG.** Define and invoke an
inner async operation, own rejection, and return a synchronous cleanup that
aborts or invalidates stale work when needed.

**Framework types recalled from the wrong renderer.** DOM event types,
React Native events, JSX intrinsic elements, and ref shapes differ. **WRONG**
when a plausible imported type does not match the installed declarations.
Inspect the actual prop or handler declaration rather than asserting it.

**Optional props defaulted with `||`.** Valid `0`, `false`, or empty-string
props are replaced. **WRONG** when those values are meaningful. Use `??` or a
parameter default, accounting for `exactOptionalPropertyTypes`.

## Configuration escapes

**Disabling `strict` to fix one error.** Broadly removes checks and hides the
model defect. **UNIDIOMATIC** at best and **WRONG** when it admits the known
failure. Fix the boundary or request a scoped, documented compatibility
decision from the surgeon.

**Permanent `skipLibCheck` as a source-code fix.** It skips checking declaration
files and can hide conflicting library declarations; it does not validate a
bad runtime package. Existing projects may use it for build cost or migration.
Changing that policy is the surgeon's decision. Do not recommend it merely to
silence an application error.

**Unverified suppression.** `@ts-ignore`, a broad ESLint disable, or a made-up
rule exception hides future failures. **UNIDIOMATIC** when a typed workaround
exists; **WRONG** when it masks a reachable mismatch. If suppression is the
only version-compatible option, keep it on the smallest line with the reason
and an issue or removal condition the project actually tracks.
