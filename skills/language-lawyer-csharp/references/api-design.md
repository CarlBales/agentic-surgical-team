# C# and .NET API Design

A public .NET API is both source and metadata consumed by other assemblies,
languages, tools, serializers, and runtimes. Review it against the target
framework and the
[Framework Design Guidelines](https://learn.microsoft.com/en-us/dotnet/standard/design-guidelines/),
not against one caller in the current repository.

## Shape the smallest public surface

Default to `private`, then widen only for a real consumer. Every public or
protected member becomes a compatibility promise. Public dependency types
also become part of that promise.

- Prefer a cohesive type over a bag of static helpers when state or policy is
  involved.
- Prefer concrete parameter types unless callers need substitution. An
  interface with one implementation and no consumer seam is not inherently
  cleaner.
- Accept the least powerful abstraction that expresses the contract, but do
  not erase useful guarantees. `IEnumerable<T>` promises less than
  `IReadOnlyList<T>`; neither promises immutability.
- Return collections callers cannot mutate when mutation is not part of the
  contract. Wrapping a mutable list as `IReadOnlyList<T>` does not stop the
  owner from changing it later.
- Avoid exposing a third-party package type unless tracking that package's API
  changes is intentional.

A public member added "just in case" is **UNIDIOMATIC**. Removing it later can
be breaking.

## Framework naming

Use the established .NET vocabulary:

| Element | Convention |
|---|---|
| namespaces, types, public members | `PascalCase` |
| parameters and locals | `camelCase` |
| interfaces | `I` plus a noun or adjective, such as `IDisposable` |
| event-argument types | `EventArgs` suffix |
| exception types | `Exception` suffix |
| task-returning asynchronous operations | `Async` suffix |
| routine `bool` query | readable predicate such as `CanRead`, `IsEmpty`, `TryGet` |

Do not encode the type in a parameter name or use unexplained abbreviations.
Match domain terms consistently. Renaming a public symbol for style alone is
usually not worth a breaking change; report that trade-off.

Properties represent values and should be cheap, quick, and unsurprising.
A property that starts network I/O, mutates durable state, or throws routinely
is **UNIDIOMATIC**; use a method whose name exposes the action. Indexers should
feel like collection access, not arbitrary computation.

## Parameters and return values

- Put required parameters before optional ones. Avoid long runs of adjacent
  booleans; an enum or options type states intent.
- Validate public arguments at the boundary. `ArgumentNullException` and
  `ArgumentOutOfRangeException` identify caller contract violations. Use
  `ArgumentNullException.ThrowIfNull` only when every target framework offers
  it, or provide the baseline-compatible check.
- Do not return `null` for an empty collection. Return an empty collection or
  sequence unless absence has a distinct meaning.
- Avoid `ref` and `out` except for interop and the established `Try` pattern.
  They complicate async methods and non-C# callers.
- A cancellation token conventionally comes last, before optional progress or
  callback parameters only when established project style requires it.
- Do not add optional parameters casually. Default values are commonly baked
  into compiled call sites, so changing a default does not update old callers.

A convenience overload that delegates to one full implementation is often
clearer than several implementations that can drift.

## Nullable reference contracts

Nullable reference types are compile-time annotations and flow analysis. They
do not add runtime null checks, and metadata from an oblivious assembly has an
unknown contract.

- `string` means callers should not pass or receive null in an enabled
  annotation context; `string?` makes absence part of the contract.
- Validate non-null public inputs even when annotations warn callers. Code from
  older C#, reflection, serializers, and other .NET languages can still pass
  null.
- Annotate the contract, not the current implementation. Returning `T?` merely
  because one branch is unfinished weakens every caller.
- Do not use the null-forgiving operator `!` as validation. It changes analysis
  only and has no runtime effect.
- Generic `T?` semantics depend on constraints and language version. Read the
  actual declaration before recommending an annotation.

Use `System.Diagnostics.CodeAnalysis` attributes when a relationship cannot be
expressed by `?` alone:

- `[NotNullWhen(true)]` for a `Try`-style boolean that proves an output non-null;
- `[MaybeNull]` when a nominally non-null generic return may be null;
- `[AllowNull]` or `[DisallowNull]` when input and output null states differ;
- `[MemberNotNull]` when a helper establishes field initialization.

These attributes are promises to the compiler and caller. A false annotation
that suppresses a real path is **WRONG**. The minimal fix is the truthful
annotation or implementation change, not another `!`.

Changing nullability on a public API may be metadata-compatible yet source
breaking for consumers that treat warnings as errors. Record it in release
compatibility review.

## Exceptions and the `Try` pattern

Throw exceptions for failures the operation cannot represent as normal
control flow. Use the `TryX` pattern when failure is expected and common, as
with parsing or dictionary lookup.

```csharp
public bool TryParse(string text, [NotNullWhen(true)] out Value? value)
{
    // Return false for an expected parse miss; do not throw for that miss.
}
```

Guidelines:

- throw the most specific standard exception that describes a caller error;
- define a custom exception only when callers benefit from catching that
  semantic category;
- preserve the original exception as `InnerException` when translating;
- rethrow with `throw;`, never `throw ex;`, which resets the visible stack;
- do not return a sentinel and also throw for the same failure class;
- propagate cancellation as `OperationCanceledException`, not ordinary
  failure;
- document exceptions callers can reasonably handle, not every implementation
  exception.

A blanket `catch (Exception) { return false; }` is **WRONG** when it converts
I/O failure, cancellation, or a programming defect into a parse miss. Catch
only the expected exception at the boundary that can handle it.

Result/discriminated-union packages can be appropriate, but they are a design
choice and a dependency, not automatically more idiomatic than exceptions.
The surgeon chooses that architecture.

## Records, `init`, and `required`

Records provide synthesized equality, printing, deconstruction, and `with`
support. A record class has reference storage with value-oriented equality; a
record struct is a value type. Use records when those semantics are the
contract, not merely to save constructor syntax.

- A `with` expression performs a shallow copy. Referenced mutable collections
  remain shared.
- Synthesized equality composes member equality. Arrays, for example, retain
  their normal reference-based equality unless wrapped or customized.
- Record inheritance participates in equality rules. Changing record shape or
  base type can change observable equality and serialization.
- `init` prevents ordinary assignment after initialization but does not make
  referenced objects immutable.
- `required` makes object initialization a compile-time obligation for aware
  C# callers. Reflection, serializers, older compilers, and dishonest
  `[SetsRequiredMembers]` use can bypass the intended invariant.

Adding a required member to a public type is source breaking for existing
object initializers. Changing `set` to `init` is also source breaking for
callers that mutate after construction. Report both as **WRONG** when the
release promises compatibility and no migration is provided.

## Immutability

Immutability is transitive only when the whole reachable state is immutable.
A get-only property returning a mutable `List<T>` is not an immutable API.

Prefer:

- constructor-established invariants;
- get-only properties and `readonly` fields;
- immutable value objects for identifiers and quantities;
- defensive copies at trust boundaries when ownership cannot be transferred;
- immutable collections when snapshot semantics are required.

Do not copy reflexively. Copying a large buffer at every layer may be worse
than a clear ownership contract. State who may mutate and for how long.

A mutable struct is especially hazardous because property access and
assignment can create silent copies. Make value types immutable unless the
mutation semantics are unmistakable and measured.

## Dependency injection conventions

Constructor injection makes required dependencies explicit and leaves a type
valid after construction. Avoid resolving routine dependencies from
`IServiceProvider`, static service holders, interfaces without a substitution
seam, scoped dependencies captured by singletons, and disposal of injected
objects owned by the container. Primary constructors or `TimeProvider` are
options only when the language/framework baseline provides them.

Container registration and lifetime architecture are the surgeon's or
platform role's decision. The lawyer judges whether the C# surface states
dependencies and ownership honestly.

## Compatibility of public APIs

Check source, binary, behavior, serialization, and reflection separately. A
change can preserve one and break another.

Usually breaking:

- removing, renaming, moving, or reducing accessibility;
- changing signatures, generic arity/constraints, sync to async, or `Task<T>`
  to `ValueTask<T>`;
- adding an abstract member, or relying on a default interface member on an
  unsupported runtime;
- sealing a type/member or changing virtual dispatch, equality, hash, order,
  or exception behavior;
- adding an ambiguous overload or changing an optional default already baked
  into callers;
- changing serialized names, enum values, constructors, `set` to `init`, or
  adding `required`.

Adding enum members, stronger nullable annotations, changed disposal or
synchronization, exposed dependency replacements, and a higher runtime floor
also need compatibility evidence. Use an API comparison tool only at L1 when
the project selected it; tool output cannot prove behavioral compatibility.

## VB.NET and CLS consumers

When the baseline says VB.NET or another CLS language consumes the assembly,
inspect the public metadata from that consumer's perspective. Case-only member
names, unsigned numeric types, pointer types, overloads distinguished only by
features the consumer cannot express, and optional/default parameter choices
can make an otherwise valid C# API awkward or inaccessible.

Apply `[CLSCompliant(true)]` only when the assembly intends that contract, then
honor its compiler diagnostics. Do not impose CLS compliance on an internal
C#-only assembly. Reviewing VB implementation style belongs to the matching
language lawyer; this section concerns the C# assembly boundary only.

## Documentation at the code boundary

XML documentation for public C# symbols and runnable code examples are part of
the API contract and belong here. State parameter nullability, exceptions,
thread safety, ownership/disposal, cancellation, and units where they are not
obvious. Do not promise implementation details.

README structure and narrative prose belong to the editor. A missing XML
summary is not automatically **WRONG**; a false ownership or nullability
statement is.
