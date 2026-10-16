# Python API Design

A Python public API is a promise across source, runtime behavior, type checkers,
and supported interpreter versions. Use the baseline's Python and package
versions. Primary authorities are [PEP 8](https://peps.python.org/pep-0008/),
the [typing specification](https://typing.python.org/en/latest/spec/), and the
versioned [standard library](https://docs.python.org/3/library/).

## Naming in Python's grain

Follow the surrounding project first, then PEP 8:

| Item | Conventional form | Example |
|---|---|---|
| modules, functions, methods, variables | `lowercase_with_underscores` | `load_record` |
| classes and most type aliases | `CapWords` | `RecordStore` |
| constants | `UPPER_CASE_WITH_UNDERSCORES` | `DEFAULT_LIMIT` |
| internal names | leading underscore | `_parse_line` |
| exception classes | `CapWords`, usually `Error` suffix | `DecodeError` |
| type variables | short caps or descriptive `CapWords` | `T`, `PayloadT` |

Names describe meaning, not implementation history. `data`, `result`, and
`manager` in a public signature are **UNIDIOMATIC** when the domain offers a
precise noun. Renaming an established public symbol for aesthetic purity is
**TASTE** unless a compatibility plan exists.

Do not use a trailing underscore except to avoid a keyword or damaging name
collision. Double-leading underscores trigger class name mangling; they are not
a general privacy mechanism. Dunder names are reserved for specified protocols.
Inventing `__serialize__` because it looks official is **UNIDIOMATIC** and may
collide with future protocol space; choose an ordinary public or private name.

## Public surface and imports

A leading underscore marks an item as non-public by convention. It is not access
control. `__all__` explicitly defines names exported by `from module import *`
and is useful as an auditable module surface. It does not prevent direct import,
and absence of `__all__` does not automatically make every non-underscore name
a supported API.

For a package, expose deliberate entry points from `__init__.py` without
re-exporting every implementation detail. Re-exported names become compatibility
commitments. A refactor that removes `package.Widget`, even if
`package.internal.Widget` remains, is **WRONG** when the former was documented
public API.

Keep imports acyclic and cheap. Network access, environment mutation, thread
creation, and substantial computation at import time are **WRONG** for a library
unless the API explicitly promises them. Registration side effects can be
valid, but document and test their ordering.

`__all__` should contain strings naming real attributes. Generated code often
lists stale names or objects rather than strings; that is **WRONG**. In stub
files, imported names are not automatically re-exported in the same way users
may expect; use explicit re-export forms consistent with the typing spec.

## Type hints are contracts, not enforcement

Annotations do not ordinarily validate values at runtime. A function annotated
`count: int` still receives any object a caller passes unless code or a framework
checks it. Describing annotations as runtime safety is **WRONG**.

Use types to express caller-relevant guarantees:

- Accept behavior with `Iterable`, `Sequence`, `Mapping`, or a `Protocol` when
  the implementation needs only that behavior. Return concrete collections when
  callers benefit from their concrete operations and ownership.
- Prefer `T | None` on Python 3.10+; use the spelling supported by the minimum
  version and annotation evaluation policy. Syntax availability and runtime
  evaluation are separate questions.
- Keep `Any` at untyped boundaries and narrow it promptly. `Any` suppresses type
  checking in both directions; adding it to silence a diagnostic is usually
  **UNIDIOMATIC**, and **WRONG** if the report claims the contract was verified.
- Use `object` when a value may be anything but operations must be checked before
  use. `Any` and `object` are not interchangeable.
- Use `TypeGuard` or `TypeIs` only on versions and checker releases that support
  their precise narrowing semantics. Do not invent narrowing from a boolean.
- Mark intentionally non-returning paths with `Never` only when they truly do
  not return normally.

Forward-reference behavior depends on Python version and whether
`from __future__ import annotations` is active. Libraries that inspect
annotations with `typing.get_type_hints` can evaluate names and must supply the
right namespaces. Do not solve import cycles by quoting types without checking
how runtime consumers resolve them.

## Protocols, ABCs, and duck typing

A `Protocol` describes structural behavior for static checkers. It is appropriate
when consumers need a small capability owned by neither concrete type. Keep it
minimal and consumer-shaped:

```python
from typing import Protocol

class Reader(Protocol):
    def read(self, size: int = -1) -> bytes: ...
```

Do not require unrelated methods merely because existing implementations have
them. That makes substitution harder and is **UNIDIOMATIC**.

`@runtime_checkable` permits limited `isinstance`/`issubclass` checks against a
protocol, but the runtime check verifies attribute presence, not full signatures
or type annotations. Treating it as runtime contract validation is **WRONG**.
Use an abstract base class when shared implementation, nominal registration, or
runtime identity is part of the design. Use ordinary duck typing when no static
or runtime abstraction earns its cost.

Variance and mutable attributes are frequent protocol traps. A writable
attribute cannot safely be covariant. Prefer a read-only `@property` in the
protocol when implementers may expose a narrower concrete value.

## Stubs, overloads, and checker boundaries

A `.pyi` file is a public type surface and must match runtime names, call shapes,
default availability, decorators, and exceptions relevant to control flow.
A stub-only symbol that runtime users can import only under `TYPE_CHECKING` is
**WRONG** unless it is explicitly type-only.

Overloads describe distinguishable caller cases. Their implementation follows
the overload declarations and must accept every case; checkers generally inspect
the declarations for callers. Overlapping overloads with incompatible returns,
or an implementation narrower than an overload, are **WRONG**. If one union
signature says the same thing, preferring it is often clearer.

Use targeted suppressions only after proving a checker limitation. Include the
checker-specific code when supported and a reason. A blanket module ignore or
`# type: ignore` without a code hides unrelated regressions and is
**UNIDIOMATIC**.

## Functions and call evolution

Use keyword-only parameters after `*` when names carry meaning, especially for
booleans, units, retry policy, or several same-typed values:

```python
def connect(address: str, *, timeout: float, verify: bool = True) -> Client:
    ...
```

`connect(host, 2.0, False)` is harder to review and locks parameter order into
the public contract. Adding an optional keyword-only parameter is usually easier
to evolve. Positional-only parameters before `/` are useful when names should
not become API, as with built-ins or wrappers that forward arbitrary keywords;
do not use them merely because the syntax exists.

Avoid boolean parameters that select substantially different operations. Two
named functions or an enum can make the contract clearer. Whether that split is
worth it is **TASTE** until ambiguity causes misuse.

Defaults are part of compatibility. Use an immutable default or sentinel, and
do not change a default's meaning silently. Accept dependencies such as clocks,
random sources, or clients at a boundary when deterministic behavior matters;
do not turn every helper into a dependency-injection framework.

Return a stable result shape. A tuple whose positions need comments is
**UNIDIOMATIC**; a `NamedTuple`, frozen dataclass, or small class may expose the
meaning. Returning internal mutable storage is **WRONG** when callers can violate
class invariants; return an immutable view, iterator, or deliberate copy.

## Dataclasses, attrs, Pydantic, and ordinary classes

Choose by required semantics, not popularity:

| Need | Default judgment |
|---|---|
| Internal value carrier with generated init/repr/equality | `dataclasses.dataclass` |
| Fine-grained converters, validators, slots, or evolution features accepted as a dependency | attrs, after version and dependency review |
| Parsing and validating untrusted or serialized boundary data | Pydantic, when its versioned coercion/strictness model fits |
| Invariants, behavior, custom construction, or stable hand-written API | ordinary class |

A dataclass does not validate annotations. `frozen=True` prevents generated
attribute assignment but does not deeply freeze contained objects. Claiming
either is **WRONG**. Use `default_factory` for mutable per-instance defaults.
Consider `slots=True` only on a supported Python version and after checking
inheritance, weak references, serialization, and consumers expecting `__dict__`.

attrs and Pydantic are third-party contracts. Their major versions differ in
APIs and semantics; never review remembered Pydantic v1 behavior against v2.
Do not introduce either merely to avoid writing a five-line class. Conversely,
hand-written ad hoc validation at a complex external boundary may be
**UNIDIOMATIC** when the project already standardizes on a validator.

## Exception APIs

Define a package or subsystem base exception derived from `Exception` when
callers need one catch point. Derive specific errors beneath it and preserve the
underlying cause with `raise ... from ...`. Exceptions intended for callers
should expose stable structured attributes; message text alone is a brittle API.

Do not derive application errors from `BaseException`; that family is reserved
for control-flow events ordinary `except Exception` should not absorb. Do not
return `None` for failure when `None` is also a valid result. Use an exception or
an explicit result object according to established project policy.

Catch only where the code can recover, translate abstraction, or add useful
context. Logging and re-raising at every layer duplicates output. Swallowing an
exception after logging is **WRONG** if callers require failure signaling.
Exception class names and documented attributes are compatibility commitments.

## Paths and filesystem boundaries

Accept `os.PathLike[str] | str` when callers naturally hold either, then convert
once with `Path(path)` at the boundary. Use `pathlib.Path` for joins, suffixes,
parents, iteration, and filesystem operations instead of manual separators or
string concatenation. This is usually **UNIDIOMATIC**, not automatically wrong.

Do not coerce arbitrary user text into a path and assume containment. Resolve and
validate against the intended root with attention to symlinks and time-of-check
to time-of-use races; security judgment may need a security reviewer. `Path`
does not make traversal safe by itself.

Use text encodings explicitly and distinguish paths from URLs. `Path("https://…")`
is a filesystem path, not a URL parser. Avoid converting `Path` to `str` until an
API actually requires it; premature conversion loses path operations and can
reintroduce platform-specific separators.

## Public compatibility review

For every public change ask:

1. Was a name removed, moved, newly re-exported, or made private?
2. Did parameter position, name, default, accepted type, or exception behavior
   narrow existing callers?
3. Did a return type, mutability promise, iteration order, or sync/async shape
   change?
4. Do `.py`, `.pyi`, docs, and runtime introspection agree?
5. Does the implementation use syntax and standard-library APIs available at
   `requires-python`?
6. Does a new dependency type leak into public annotations or return values?
7. Is deprecation staged in the project's established mechanism and release
   policy rather than silently breaking callers?

Source compatibility, runtime compatibility, and typing compatibility are three
different claims. State which one a finding concerns.
