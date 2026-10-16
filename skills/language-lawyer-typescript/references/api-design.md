# TypeScript API Design

A public TypeScript surface is both a runtime module and a compile-time
promise. Review the JavaScript entry point, declarations, package metadata,
and supported module resolvers together. A clean `.ts` signature is not
useful if consumers load a different file or receive a different declaration.

Use the TypeScript
[module reference](https://www.typescriptlang.org/docs/handbook/modules/reference.html),
[declaration-file handbook](https://www.typescriptlang.org/docs/handbook/declaration-files/introduction.html),
and the runtime's versioned package documentation as authority.

## Export only the intended contract

Prefer explicit exports from a package entry point. Every exported value and
type becomes a compatibility obligation.

```ts
export { createClient } from "./client.js";
export type { Client, ClientOptions } from "./types.js";
```

With configurations that preserve module syntax, `export type` and `import
type` make erasure explicit and prevent a type-only dependency from becoming
a runtime import. A type-only import cannot be used as a runtime value.
Generated code often imports a class with `import type` and then calls its
constructor; that is **WRONG**.

Default versus named export is normally **TASTE**. Match the package's stable
convention. Named exports make refactors and multi-symbol modules explicit;
default exports can fit one-primary-value modules. Do not manufacture a
correctness rule from that preference.

Avoid exporting implementation-only helper types. Explicit return types on
public functions catch accidental leakage of private classes, dependency
types, and unstable inferred unions. Redundant annotations on local values
are usually noise; annotations at a publication boundary are a compatibility
tool.

## Object shapes, unions, and extension

Choose `interface` when declaration merging or an explicitly extensible object
contract is wanted. Choose `type` for unions, mapped and conditional types,
primitives, and closed aliases. For an ordinary closed object shape either is
defensible, so report it as **TASTE** at most.

A discriminated union states which combinations are valid:

```ts
export type LoadState<T> =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "ready"; value: T }
  | { status: "failed"; error: Error };
```

A bag of optional `loading`, `value`, and `error` properties admits
contradictory states. It is **UNIDIOMATIC** when callers repeatedly reconstruct
the invariant, and **WRONG** when an admitted state reaches code that assumes
one field exists.

Adding a member to an exported union can break exhaustive consumers. Adding a
required property breaks object construction. Making an optional property
required, narrowing a parameter, or widening a return type can also break
callers. Judge compatibility against declarations produced by the previous
release, not intuition about source edits.

## Input and output types

Accept the least authority the implementation needs:

- `readonly T[]` when the function only reads an array;
- `Readonly<T>` for a shallow read-only view, without claiming deep runtime
  immutability;
- a narrow object interface rather than a concrete class when identity and
  private state do not matter;
- `unknown` plus a validator at an untrusted boundary;
- a specific union instead of `string` when the set is truly closed.

Do not accept a broad `Record<string, unknown>` merely to avoid naming a real
input shape. Conversely, generic abstractions that expose five type parameters
to model one concrete operation are **UNIDIOMATIC** when callers cannot infer
them.

Return types should preserve facts callers need without exposing internal
machinery. Returning a mutable array permits caller mutation; return
`readonly T[]` when mutation is not part of the contract. Returning a
library's internal dependency type makes that dependency and its version part
of the public surface.

Overloads are appropriate when input and output types are correlated in ways
a union signature would erase. The implementation signature is not visible to
callers and must handle every overload. Prefer a union parameter when the
return type does not vary. A long overload list generated from examples often
belongs in one generic or discriminated union.

## Branded and opaque values

Structural typing lets unrelated strings mix. A brand creates a compile-time
distinction while retaining the runtime representation.

```ts
declare const userIdBrand: unique symbol;
export type UserId = string & { readonly [userIdBrand]: "UserId" };

export function parseUserId(value: string): UserId | undefined {
  return isValidUserId(value) ? (value as UserId) : undefined;
}
```

The assertion is localized after validation. Do not export a public cast that
lets any string become `UserId`; that defeats the contract. A brand supplies
no runtime validation, serialization tag, or security boundary. Claiming it
does is **WRONG**.

Brands are **UNIDIOMATIC** when used for every incidental primitive. Use them
where mixing values is plausible and costly: identifiers, validated strings,
units, or normalized paths. Keep the branding symbol private unless consumers
must construct compatible types intentionally.

## Error signaling

Use one failure channel per operation and make expected failures inspectable.
The right shape depends on the API:

- throw or reject for failures that abort an operation;
- a discriminated result for expected outcomes callers routinely branch on;
- `undefined` only when absence has no useful explanation;
- never encode a recoverable error as a rejected promise in one overload and
  a result value in another.

Catch variables are `unknown` when `useUnknownInCatchVariables` is in effect
(as enabled through relevant strict settings in supported compiler versions).
Narrow before reading `.message`, because JavaScript permits throwing any
value.

```ts
try {
  await writeRecord(record);
} catch (error: unknown) {
  if (error instanceof Error) throw error;
  throw new Error("write failed with a non-Error value");
}
```

Preserve the original cause only with a runtime-supported mechanism from the
baseline. Do not assume all declared targets support a recently added `Error`
constructor option. Error messages must not contain tokens, credentials, or
unredacted sensitive payloads; security impact goes to the security reviewer.

An `async` function reports thrown failures as rejected promises. A `try`/
`catch` around a call without `await` does not catch its later rejection. That
is **WRONG** when the code claims to translate the failure; return the promise
with `.catch(...)` or await it inside the `try`.

## Declaration files

Treat emitted `.d.ts`, `.d.mts`, and `.d.cts` files as release artifacts.
At L1, inspect declaration output using the repository's configured build.
`declaration: true` emits declarations with other outputs;
`emitDeclarationOnly: true` suppresses JavaScript, not declaration artifacts.
Both are writes and never L0 operations.

A hand-written declaration must describe runtime truth:

```ts
// WRONG when the JavaScript can return undefined.
export declare function find(id: string): Item;

// Matches the runtime possibility.
export declare function find(id: string): Item | undefined;
```

Ambient declarations can make nonexistent modules and members type-check.
Each `declare module` or global augmentation needs a corresponding runtime
provider. Keep global declarations minimal, avoid top-level pollution, and
verify that a declaration file is included by the consumer configuration.

Do not copy declarations from a newer package version into an older runtime.
That creates code which compiles and fails when loaded. Prefer declarations
shipped by the package; if a separate `@types` package is required, its major
compatibility and resolution belong in the baseline.

Declaration rollup tools can change symbol names, inline dependency types, and
expose paths that source review misses. Their output is `Unverified` until it
is generated at L1 or supplied as an order input.

## ESM and CommonJS

Establish format from all of these together:

- `package.json` `type` and `exports`;
- source extensions `.mts`, `.cts`, `.ts`, and `.tsx`;
- compiler `module` and `moduleResolution`;
- output extensions and directories;
- the Node.js, bundler, browser, or React Native resolver actually used.

Under Node-aware TypeScript modes, relative ESM imports normally name the
runtime extension, such as `./client.js`, even when the source is
`client.ts`. Bundler-oriented resolution follows different rules. Applying
one mode's import advice to another is **WRONG** when it produces output the
host cannot resolve.

`.mts` and `.cts` force module intent. TypeScript declaration output follows
with `.d.mts` and `.d.cts`; JavaScript output uses the corresponding runtime
module extensions. Plain `.ts` interpretation can depend on the nearest
`package.json` and compiler mode.

An exports map defines public runtime entry points and can block undeclared
deep imports. Types must describe the same condition and subpath selected at
runtime. Verify condition ordering and supported conditions against the
pinned TypeScript and Node.js documentation rather than copying a current
snippet into an older package.

## Dual-package hazards

Publishing both ESM and CommonJS is not just producing two syntax variants.
If one process loads both builds, it can receive two instances of module
state, two constructor identities, and objects that fail `instanceof` across
the boundary. Side effects may run twice.

A dual package must answer:

1. Do both entries expose the same names and behavior?
2. Do their declarations resolve to the matching runtime entry?
3. Is shared singleton state safe if both formats load?
4. Are relative imports and file extensions valid in each output?
5. Can each supported consumer resolve only documented subpaths?

A hand-written second implementation is **UNIDIOMATIC** because the surfaces
drift. Producing two wrappers around one stateful core may still duplicate the
core depending on the host. The surgeon chooses whether dual support is worth
that complexity; the lawyer identifies the concrete compatibility cost.

Publishing, tagging, and modifying a registry are L3. At most, an L1/L2 order
may stage package metadata and generated artifacts. The report describes the
surgeon-owned publication command without running it.

## Public React and JSX types

For `.tsx`, read the effective `jsx` option and the framework versions before
judging emitted or preserved JSX. Component props are a public object shape;
export them only when consumers need them. Do not add `children` implicitly
unless the component accepts it, and do not claim that a framework helper
behaves a certain way without version-matched declarations.

Event and element types should come from the installed framework declaration,
not from plausible names recalled from another version or renderer. Browser,
React Native, and custom JSX runtimes do not share every host type. A made-up
handler or element type is **WRONG**; inspect the actual declaration source.
