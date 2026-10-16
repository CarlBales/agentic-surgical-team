# Type System and Runtime Semantics

TypeScript is a structurally typed, gradually typed checker for JavaScript.
Its types are erased. Acceptance by `tsc` says that the program fits the
checker model under one configuration; it does not validate external values
or remove JavaScript's runtime behavior.

Use the [TypeScript Handbook](https://www.typescriptlang.org/docs/handbook/intro.html),
the [TSConfig Reference](https://www.typescriptlang.org/tsconfig/), and the
[ECMAScript specification](https://tc39.es/ecma262/) for the versions in the
baseline. This file is a review map, not a replacement for them.

## Start at the untyped boundary

`JSON.parse` returns `any` in the standard library declarations. Assign the
result to `unknown` immediately, then validate it.

```ts
// WRONG: an assertion is not validation.
const config = JSON.parse(text) as Config;
start(config.port);

// Boundary is contained; the guard must check every property it promises.
const candidate: unknown = JSON.parse(text);
if (!isConfig(candidate)) {
  throw new Error("invalid configuration");
}
start(candidate.port);
```

The first form is **WRONG** when `text` can violate `Config`: the code claims a
runtime fact it never established. The same rule applies to `fetch().json()`,
storage, messages, environment variables, and untyped JavaScript packages.
A schema library is useful only when the returned inferred type and runtime
schema stay connected; verify that connection for the pinned package version.

Use `unknown` when a value exists but its type is not established. Narrow it
before use. Use `any` only at a deliberate compatibility boundary and prevent
it from spreading. `any` is assignable both ways, permits arbitrary member
access, and can silently contaminate generic inference. Replacing a needless
`any` with `unknown` is **UNIDIOMATIC** cleanup; allowing an invalid runtime
value through a purported validator is **WRONG**.

## Narrowing and control-flow analysis

TypeScript narrows a variable from checks and tracks assignments and reachable
control flow. Prefer evidence the runtime actually provides:

- `typeof`, with the JavaScript caveat that `typeof null === "object"`;
- `Array.isArray` for arrays;
- `instanceof` only when constructor identity is stable across realms and
  package copies;
- discriminant equality for tagged unions;
- property-presence checks with `in`, remembering that presence and a value of
  `undefined` are distinct;
- user-defined predicates only when their implementation proves the stated
  predicate for every `true` result.

```ts
function length(value: string | readonly unknown[]): number {
  if (typeof value === "string") return value.length;
  return value.length;
}
```

A predicate such as `function isUser(x: unknown): x is User` is trusted by the
checker. If it checks only `typeof x === "object"`, its signature overclaims.
That is **WRONG** at the boundary; fix the implementation or weaken the
predicate.

Truthiness is not presence. `if (count)` removes `0`, and `name || fallback`
replaces the empty string. Use an explicit comparison or `??` when only
`null` and `undefined` are absent. Calling every truthiness check wrong is
itself poor review; the domain may exclude the falsy values.

Narrowing can be invalidated by mutation the checker cannot see. A callback or
alias may change an object after a property check. Copy the narrowed value to
a local before an asynchronous or effectful boundary when mutation is
possible.

## Optional properties and indexed access

With `exactOptionalPropertyTypes`, `value?: T` means the property may be
absent; assigning `undefined` is allowed only if `undefined` is part of `T`.
Without it, assignment treats absence and explicit `undefined` more loosely.
The runtime still distinguishes them with `in`, enumeration, and object
spread. Do not recommend a fix until the effective option is known.

`noUncheckedIndexedAccess` adds `undefined` to reads through index signatures
and ordinary array indexes that are not statically known. Without it,
`items[i]` has `T` even when `i` is out of range. That is a deliberate
soundness hole, not proof that the element exists.

```ts
// WRONG if values may be empty.
return values[0].trim();

// The model admits absence.
const first = values[0];
return first === undefined ? undefined : first.trim();
```

Changing the first line to `values[0]!.trim()` only silences the checker. A
non-empty tuple such as `readonly [T, ...T[]]` is the type-level fix when the
caller really guarantees non-emptiness; a runtime check is the fix otherwise.

## Structural typing and excess properties

Compatibility depends on members, not declarations. Two independently named
interfaces with the same shape are compatible. This is convenient for plain
data and risky for identifiers and units.

Excess-property checks are intentionally limited. A fresh object literal may
be rejected for an extra property, while the same value held in a variable is
accepted structurally.

```ts
type Point = { x: number; y: number };
const value = { x: 1, y: 2, colour: "red" };
const point: Point = value; // accepted; extra data still exists at runtime
```

Do not describe a TypeScript type as an exact object schema. If exactness
matters at an I/O boundary, validate keys at runtime. If two strings must not
mix, use an opaque or branded type with a validating constructor; see
[API design](api-design.md).

`readonly` is also structural and shallow. It prevents writes through that
reference; it does not freeze the object or recursively protect nested data.
Claiming that a `Readonly<T>` value is immutable at runtime is **WRONG**.

## Variance and callback parameters

With `strictFunctionTypes`, function-type parameters are checked
contravariantly. Method declarations are excluded for compatibility and remain
bivariant, so a method accepting `Dog` can be admitted where callers may pass
any `Animal`. Report **WRONG** only when that wider call is reachable; use a
function property `(value: Animal) => void` or accept the full input.

Mutable arrays expose another deliberate hole: a narrower array can be viewed
as wider and then receive an incompatible value. Accept `readonly T[]` when a
callee only reads. Contextual `() => void` also permits a value-returning
function; an async callback can therefore create an ignored promise.
`@typescript-eslint/no-misused-promises` checks supported cases.

## Generics and constraints

Constraints state what an implementation may use; preserve relationships
instead of asserting them back into existence.

```ts
function get<T extends object, K extends keyof T>(value: T, key: K): T[K] {
  return value[key];
}
```

`object` excludes primitives. `{}` means any non-nullish value, while
`Record<string, unknown>` requires string-keyed properties. A generic used
only once may add no relationship. `parse<T>(text: string): T` cannot safely
produce arbitrary `T`; accept a decoder `(unknown) => T` or return `unknown`.

Conditional types distribute over a naked type parameter. Wrap both sides in
tuples when asking about a union as a whole. Avoid defaults such as `T = any`
that silently leak unchecked values.

## `satisfies`, assertions, and non-null assertions

`satisfies` checks compatibility while retaining useful inference; it does
not alter or freeze the runtime value.

```ts
const routes = {
  home: "/",
  settings: "/settings",
} as const satisfies Record<string, `/${string}`>;
```

Use an annotation when consumers should see that abstraction and `satisfies`
when checking without needless widening. For a local constant, the choice is
often **TASTE**.

`as T` does not convert or validate. `as unknown as T` disables the overlap
check and needs a written invariant. Angle-bracket assertions conflict with
JSX syntax in `.tsx`. Postfix `!` removes nullish types without checking;
replace it with a guard, better state model, or constructor-established
invariant when absence is reachable.

## Discriminated unions and exhaustiveness

Model meaningful states explicitly:

```ts
type Result<T> =
  | { kind: "ok"; value: T }
  | { kind: "error"; error: Error };

function assertNever(value: never): never {
  throw new Error(`unhandled variant: ${String(value)}`);
}
```

Calling `assertNever(result)` in the final branch makes a new variant a type
error. A silent default hides it. Exported-union additions can therefore break
exhaustive consumers. Open plugin protocols may instead need an unknown
fallback; closed versus open is an API decision, not style law.

## Declaration merging

Interfaces in one declaration space can merge; namespaces can merge under the
documented rules. Module augmentation changes the type view of the exact
module specifier but creates no runtime member. A fabricated augmentation is
**WRONG** when no adapter installs that member. Global augmentation affects
the whole compilation; keep it minimal and prefer a type alias when extension
is not a contract.

## Async and the event loop

An async body runs synchronously until its first suspension and always returns
a promise. Continuation after `await` is a promise job, even for an already
fulfilled promise. A `Promise` constructor executor itself runs synchronously.

- `forEach` ignores callback promises. Use `for...of` for sequential work or
  `Promise.all(values.map(...))` for intended concurrency.
- `Promise.all` starts no work itself and rejects on one rejection while other
  work may continue; `Promise.allSettled` records every outcome.
- `void operation()` marks detachment but does not handle rejection. Attach a
  handler when completion is intentionally unowned.
- Promises have no universal cancellation; use the API's documented abort
  protocol. Unhandled-rejection behavior is host- and version-specific.

Ordering, bounds, and error aggregation are correctness when the contract
specifies them. Otherwise present the alternatives to the surgeon.
