# Python Data Model and Semantics

The hard part of Python is not its syntax. It is the interaction among names, shared objects,
protocols, exceptions, and concurrency. Judge against the project's supported minor and
implementation, then consult the versioned [Language
Reference](https://docs.python.org/3/reference/) and [Data
Model](https://docs.python.org/3/reference/datamodel.html).

## Names, binding, and scope

Assignment binds a name to an object. It does not copy the object, declare a storage cell with the
object's type, or mutate an existing object unless the target itself is an attribute, subscription,
or unpacking target.

```python
left = {"items": []}
right = left
right["items"].append("x")
assert left == {"items": ["x"]}
```

Treat `right = left` followed by independent-mutation assumptions as **WRONG**. Make the ownership
decision explicit: share intentionally, construct a new value, or copy at the boundary. A shallow
`copy.copy` or `dict.copy` still shares nested objects; use `copy.deepcopy` only when its recursive
semantics match the domain, not as a reflex.

A name assigned anywhere in a function body is local to that function unless declared `global` or
`nonlocal`. Reading it before the assignment executes raises `UnboundLocalError`; runtime branch
order does not change compile-time scope analysis.

```python
count = 0

def bump():
    print(count)  # WRONG: count is local because of the next statement.
    count += 1
```

The smallest fix is usually to pass and return state. Use `nonlocal` for state owned by an enclosing
closure and `global` only for genuinely module-owned state. Adding either merely to silence the
exception is **UNIDIOMATIC** when a parameter makes ownership clearer.

Class bodies execute in their own namespace, but methods do not close over that namespace as an
enclosing lexical scope. Comprehensions have their own implicit scope in Python 3, while assignment
expressions have context-specific binding rules. Pattern matching captures names; a bare name in a
pattern is normally a capture, not a constant comparison. Verify these against the pinned minor.

## Mutability and aliasing

Mutability belongs to objects, not names. A tuple can contain a mutable list; `Final` is a static
restriction on rebinding, not deep immutability; a frozen dataclass can still contain mutable
fields. Review the entire reachable state before calling a value immutable or thread-safe.

Class attributes are shared by instances until shadowed:

```python
class Batch:
    items = []  # WRONG if each Batch needs independent state.

    def __init__(self) -> None:
        self.items = []  # one list per instance
```

In-place operators may mutate or rebind depending on the type. `list +=` mutates the list; `tuple
+=` creates and binds a new tuple. Do not reason from spelling alone. Likewise, a function receiving
`list[T]` can mutate caller-owned state; use an immutable abstraction such as `Sequence[T]` only
when the implementation also refrains from mutation.

## Default arguments

Defaults are evaluated once, when the `def` statement executes. An accidental mutable default is
**WRONG**, not merely style:

```python
def collect(item: str, items: list[str] | None = None) -> list[str]:
    if items is None:
        items = []
    items.append(item)
    return items
```

Use a private sentinel rather than `None` when `None` is a meaningful argument. Do not automatically
rewrite an intentional shared cache: establish intent, then prefer an explicit cache object or
`functools.cache`/`lru_cache` when their hashability, eviction, and lifetime semantics fit. Ruff
`B006` documents the common case but cannot decide intent.

Defaults also capture the object bound at definition time. Rebinding a module constant later does
not alter an existing function default. That can be useful, but a default that silently freezes
environment-dependent state is often **UNIDIOMATIC**; compute it in the body or inject it.

## Closures and late binding

Closures capture variables, not snapshots of their current values. Lookup occurs when the closure is
called:

```python
funcs = [lambda: i for i in range(3)]
assert [f() for f in funcs] == [2, 2, 2]
```

If `[0, 1, 2]` was intended, this is **WRONG**. Bind a value per iteration:

```python
funcs = [lambda i=i: i for i in range(3)]
```

A small factory function is clearer when several values are captured. The default-argument form is
idiomatic for one value; choosing between them is **TASTE**. The same late-binding issue appears in
callbacks and async tasks that close over a loop variable.

## Data-model methods

Special methods are protocol contracts, not ordinary callback names. Read the matching Data Model
section before implementing a dunder.

- `__new__` creates an instance; `__init__` initializes an already-created one
  and must return `None`. Returning another value from `__init__` is **WRONG**.
- `__repr__` should be unambiguous and, when practical, constructor-like;
  `__str__` is user-facing. Leaking secrets from either is **WRONG**.
- Rich comparisons should return `NotImplemented` for unsupported operand types,
  not raise merely because the other type differs. Python may then try the
  reflected operation or fall back according to the protocol.
- Objects that compare equal must have equal hashes. Defining `__eq__` on a
  mutable value while retaining identity-like hashing breaks mappings and sets;
  report it **WRONG**.
- `__bool__` must return `bool`. In its absence, truth testing can use `__len__`;
  `__len__` must return a non-negative integer.
- Attribute hooks differ: `__getattribute__` sees every lookup and recursing
  through `self.name` can loop; `__getattr__` runs only after normal lookup
  fails. Delegate through `object.__getattribute__` when appropriate.
- Binary operator methods should preserve the distinction between unsupported
  operands (`NotImplemented`) and invalid values (an exception).

Calling `obj.__len__()` instead of `len(obj)` is usually **UNIDIOMATIC** because it bypasses normal
protocol dispatch expectations and advertises internals. Direct dunder calls are justified when
implementing the protocol itself.

## Descriptors

An object with `__get__`, `__set__`, or `__delete__` can participate in attribute lookup. A
descriptor defining `__set__` or `__delete__` is a data descriptor and takes precedence over an
instance dictionary. A non-data descriptor can be shadowed by an instance attribute. Functions are
non-data descriptors; binding produces methods. `property`, `classmethod`, and `staticmethod` are
descriptor-based.

A descriptor normally stores per-instance state on the instance, often using a name learned in
`__set_name__`. Storing changing values on the descriptor itself shares them across every owner
instance and is **WRONG** unless sharing is the declared contract. Use `WeakKeyDictionary` only
after considering object hashability, lifetime, and thread safety.

Do not invoke `descriptor.__get__` manually in application code. Use normal attribute access so
owner, instance, precedence, and inheritance are correct. Custom `__getattribute__` implementations
can accidentally bypass or duplicate descriptor logic; keep them rare and minimal.

## Iteration protocols

An iterable's `__iter__` returns an iterator. An iterator's `__iter__` returns itself and `__next__`
either returns the next item or raises `StopIteration`. Returning `None` at exhaustion is **WRONG**
because `None` may be a valid item. A fresh-container iterator may be repeatable; an iterator is
normally single-pass. Document which one an API accepts or returns.

Generator `return value` ends iteration and stores `value` on the resulting `StopIteration`. Under
PEP 479 behavior, an accidental `StopIteration` escaping a generator body is transformed into
`RuntimeError`; do not use it as an internal control-flow shortcut.

Asynchronous iteration is a separate protocol: `__aiter__` supplies an async iterator, `__anext__`
is awaitable, and exhaustion raises `StopAsyncIteration`. Mixing sync and async protocol methods
because their names look parallel is **WRONG**. An async generator should be closed so its `finally`
blocks run.

## Context managers

`with manager as value` calls `__enter__`, then always calls `__exit__` if entry succeeded.
`__exit__` receives exception information; a truthy return suppresses the exception. Returning
`True` accidentally is **WRONG**. Return `False` or `None` unless suppression is the explicit API.

Acquire resources in `__enter__` only when failure before acquisition cannot leave cleanup
ambiguous. `contextlib.contextmanager` requires exactly one yield; cleanup belongs in `finally`.
`ExitStack` is idiomatic for a dynamic number of resources. Async resources require `async with`,
`__aenter__`, and `__aexit__`; a synchronous manager that performs blocking I/O still blocks the
event loop.

## Exceptions and chaining

Catch the narrowest exception whose recovery is understood. Derive ordinary application exceptions
from `Exception`, not `BaseException`. A bare `except:` also catches `KeyboardInterrupt`,
`SystemExit`, and cancellation classes derived from `BaseException`; this is usually **WRONG**.

`raise NewError(...) from exc` records an explicit cause. Raising while handling another exception
records implicit context. `raise ... from None` hides the displayed context but does not make the
earlier failure irrelevant; use it only when translating to a complete public abstraction. A bare
`raise` inside the handler preserves the original traceback. `raise exc` changes traceback shape and
is **UNIDIOMATIC** when simple re-raising was intended.

A `return`, `break`, or `continue` in `finally` can suppress an active exception. Report suppression
as **WRONG** unless explicitly required and documented. Exception messages should add operation and
stable identifiers, never secrets. For `ExceptionGroup` and `except*`, introduced in Python 3.11,
preserve subgroup semantics rather than flattening unrelated failures into one string.

## Threads, the GIL, and free threading

The language does not promise that application invariants are protected by a GIL. On ordinary
CPython builds, the GIL permits only one thread to execute Python bytecode at a time, but code can
release it during I/O and extension calls, and a multi-step read-modify-write remains a race at the
domain level. Use `Lock`, queues, or ownership transfer around the invariant.

CPython 3.13 introduced an **experimental** free-threaded build under PEP 703. It can run with the
GIL disabled, but importing an extension not marked as free-threading compatible can enable the GIL
at runtime. Built-in containers use internal locks in that implementation, yet the 3.13 HOWTO
explicitly says concurrent-modification behavior is not a language guarantee and recommends explicit
synchronization. Record build and runtime GIL state before judging.

Code claimed to support free-threaded 3.13 must review extension compatibility, shared iterators, C
API assumptions, and synchronization. Code that is safe only because a current CPython operation
appears atomic is **WRONG** as portable thread-safe code. Alternate implementations have different
execution models.

## Asyncio and cancellation

Asyncio is cooperative concurrency. Calling an `async def` creates a coroutine object; it does not
schedule execution. A task runs until it reaches an await that actually suspends. Blocking file,
network, process, or CPU work in that path blocks the event-loop thread.

Cancellation is injected into a task as `asyncio.CancelledError` at a suspension point. In supported
modern Python it derives directly from `BaseException`. Use `try/finally` for cleanup and generally
re-raise after cleanup. Swallowing cancellation while leaving the caller to believe the task stopped
is **WRONG**. The asyncio documentation warns that structured-concurrency components use
cancellation internally; suppressing it can make `TaskGroup` and timeout behavior misbehave.

`asyncio.shield` protects the inner awaitable from the caller's cancellation; it does not make the
awaiting caller uncancelled. Timeouts cancel work according to the versioned API's contract. Keep
strong references to independently created background tasks and observe their results. Prefer
`TaskGroup` on Python 3.11+ when related task lifetimes should succeed or fail as a unit.

At each `await`, ask: what shared state has changed, which resource is held, what if cancellation
lands here, and who owns any spawned task? A lock held or a half-committed operation across an await
is a finding even in single-threaded execution because another task can run.

## Review questions

- Which names alias the same mutable object, and is that sharing intentional?
- Are default values and closures bound at the intended time?
- Does every dunder return exactly what its protocol requires?
- Can descriptor state leak across instances?
- Are iterators single-pass, exhaustion-correct, and sync/async-correct?
- Can a context manager or `finally` suppress a failure accidentally?
- Is every translated exception chained, and every broad catch justified?
- Is thread safety based on locks and invariants rather than CPython folklore?
- Can every async task be cancelled without leaked resources or partial state?
