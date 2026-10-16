# C# Async, Lifetime, and Memory

The hard part of modern C# is knowing where execution may resume, who owns a
resource, which values can escape, and what concurrency contract a type
actually offers. Judge against the selected language, framework, and runtime;
use their versioned C# and .NET documentation as authority.

## The async execution model

An `async` method starts synchronously. It runs on the caller's thread until
it reaches an await whose awaiter is not complete. It then arranges a
continuation and returns a task-like value. `async` does not itself create a
thread, make CPU work parallel, or make blocking I/O nonblocking.

```csharp
public async Task<Response> SendAsync(Request request, CancellationToken token)
{
    Validate(request);                         // synchronous
    Response response = await transport.SendAsync(request, token);
    return response;
}
```

Exceptions thrown before or after the first await are represented by the
returned `Task` once an `async Task` method has been invoked. The caller sees
them when it awaits the task. The important exception is `async void`, which
has no task on which to store completion or failure.

A task represents one eventual completion, not a thread. `Task.Run` schedules
work on the thread pool; wrapping naturally asynchronous I/O in `Task.Run`
wastes a thread and is **UNIDIOMATIC**. Use `Task.Run` only for deliberate CPU
work or to isolate a blocking API, with ownership and cancellation stated.

## Context capture and deadlocks

By default, `await` normally schedules its continuation through the current
`SynchronizationContext`, or through a non-default current `TaskScheduler`
when relevant. UI frameworks and classic ASP.NET (`System.Web`) install
contexts with affinity or request semantics. ASP.NET Core normally does not
install such a context.

```csharp
// WRONG on a context-bound thread when LoadAsync captures that context.
Result result = LoadAsync().Result;

// Fix: make the caller asynchronous too.
Result result = await LoadAsync();
```

The deadlock cycle is concrete:

1. the context thread calls `.Result` or `.Wait()` and blocks;
2. the asynchronous operation completes elsewhere;
3. its continuation is queued to the captured context;
4. the only context thread cannot run the continuation because it is blocked.

Do not claim this deadlock where no context is captured. Sync-over-async is
still hazardous in server code without a context: it ties up a worker and can
cause thread-pool starvation under load. `GetAwaiter().GetResult()` unwraps
the original exception instead of an `AggregateException`; it does not remove
the blocking or deadlock risk.

`ConfigureAwait(false)` says that this await need not resume on the captured
context. It is appropriate in context-independent reusable library code when
the baseline and project convention support it. It is not a universal fix:

- it affects one await, not callers or earlier/later awaits;
- code after it must not require UI or request-context affinity;
- it often changes nothing in ASP.NET Core, where no custom context exists;
- `CA2007` is analyzer guidance, not a language rule, and may be disabled.

Blanket insertion is **UNIDIOMATIC**. Establish the context and library/app
boundary first.

## `async void`, task observation, and cancellation

`async void` belongs only at a framework-required event-handler boundary.
The caller cannot await it, compose it, know when it finished, or reliably
catch an exception raised after suspension.

```csharp
// WRONG unless this exact signature is required for an event callback.
public async void Refresh() => await ReloadAsync();

// Fix.
public async Task RefreshAsync() => await ReloadAsync();
```

An event handler that must be `async void` should catch expected failures at
the boundary and route them through the application's established error path.
Do not hide the exception merely to avoid a crash.

Calling a task-returning method without awaiting or otherwise observing it
usually produces `CS4014`. It is **WRONG** when completion, failure, or a
scoped dependency matters. Deliberate background work needs an owner that
observes failures and coordinates shutdown; assigning to `_` documents only
that the task was discarded, not that doing so is safe.

Cancellation is cooperative:

- accept a `CancellationToken` where callers can cancel meaningful work;
- pass it to each cancellable operation;
- call `ThrowIfCancellationRequested` in CPU loops at sensible boundaries;
- let `OperationCanceledException` propagate with the relevant token;
- do not log expected cancellation as an application failure.

Catching `Exception` also catches `OperationCanceledException`. Swallowing it
turns cancellation into apparent success and is **WRONG** when the caller
relies on task state.

## `Task` versus `ValueTask`

Return `Task` by default. It is a reference with stable composition semantics
and can be awaited repeatedly. `ValueTask` is a performance tool for APIs that
complete synchronously often enough for avoided allocation to matter.

General consumer rule: consume a `ValueTask` once. A value backed by an
`IValueTaskSource` may not support multiple awaits, concurrent awaits, or
multiple calls to `AsTask`. If repeated composition is required, call
`AsTask()` once and retain that `Task`.

```csharp
// UNIDIOMATIC without a measured allocation problem.
public ValueTask<Item> GetAsync() => new(LoadAsync());

// Simpler contract.
public Task<Item> GetAsync() => LoadAsync();
```

Changing a public return type between `Task<T>` and `ValueTask<T>` is an API
change. Do not recommend it from intuition; measure the call pattern and
allocation first.

## Deterministic disposal

The GC reclaims managed memory. It does not provide timely release of file
handles, sockets, database objects, native buffers, or other scarce resources.
`IDisposable` and `IAsyncDisposable` express deterministic ownership.

```csharp
using Stream stream = File.OpenRead(path);       // Dispose at scope exit
await using Resource lease = await OpenAsync();  // DisposeAsync at scope exit
```

`using` lowers to `try`/`finally`. Multiple resources are disposed in reverse
construction order. A using declaration lives to the end of its enclosing
scope, which can be much later than a using statement; use a narrower block
when lifetime matters.

Rules:

- dispose what the method owns, not an injected or borrowed object;
- use `await using` when asynchronous cleanup is part of the contract;
- if a type implements both interfaces, document which path callers need;
- make repeated disposal harmless where practical;
- never access an object after ownership was transferred or disposal began.

A finalizer is nondeterministic, runs on a dedicated runtime thread, and must
not depend on other finalizable objects still being alive. Use one only to
protect directly owned unmanaged state, normally through `SafeHandle`.
A correct dispose pattern releases state and calls `GC.SuppressFinalize`.
Adding a finalizer to release ordinary managed objects is **WRONG**.

## GC and reachability

Collection follows reachability, not lexical scope. A local can become dead
before the end of its method; conversely, an event subscription, static cache,
or timer can retain an object indefinitely. A memory leak in managed code is
usually an unintended live reference.

Do not force `GC.Collect()` as routine cleanup. It perturbs generational
heuristics and does not dispose resources. Use memory profilers and allocation
measurements before claiming that a particular allocation matters.

Pooling changes ownership. Returning an array to `ArrayPool<T>` while a span,
memory, task, or callback can still observe it is **WRONG**. Clear sensitive
contents when the pool contract and threat model require it.

## `Span<T>`, `Memory<T>`, and escape rules

`Span<T>` and `ReadOnlySpan<T>` are ref structs: they can describe stack,
managed, or unmanaged contiguous memory without allocation, but cannot escape
the lifetime the compiler tracks. They cannot be boxed or stored as fields of
ordinary heap objects. They must not remain live across `await` or `yield`.
C# versions have changed where ref structs may appear in async and iterator
methods, so cite the project's `LangVersion`, not remembered restrictions.

Use `Memory<T>` or `ReadOnlyMemory<T>` when data must cross an asynchronous
boundary or live on the heap. Taking `.Span` creates a synchronous view; do
not retain that view across suspension.

```csharp
// WRONG: a stack-backed span cannot survive an asynchronous boundary.
Span<byte> buffer = stackalloc byte[128];
await FillAsync();
Consume(buffer);

// Fix: use owned memory whose lifetime covers the operation.
byte[] buffer = new byte[128];
await FillAsync(buffer);
```

`stackalloc` is not automatically faster. Large or input-controlled lengths
can exhaust the stack. Bound the size and measure before replacing arrays.

## Structs, classes, and copying

Choose a struct for value semantics: small, logically one value, usually
immutable, and cheap to copy. Choose a class for identity, shared mutation,
polymorphism, or large state. There is no universal byte threshold.

Hazards:

- a mutable struct is copied on assignment and property return; mutating the
  copy does not update the original — often **WRONG**;
- `default(T)` can produce a value without running the intended constructor,
  so every struct needs a valid or safely rejected zero state;
- converting a struct to an interface or `object` can box it;
- `readonly struct` and readonly fields prevent defensive-copy surprises, but
  only when the design is actually immutable;
- record structs and record classes have different identity and equality
  semantics. The keyword is not a cosmetic choice.

## Thread safety

State the unit of synchronization and the invariant it protects. "Uses a
concurrent collection" is not enough when a check-then-act sequence spans two
operations.

- Lock a private, dedicated object. Locking `this`, a `Type`, or an interned
  string exposes the lock to unrelated code and is **WRONG** when that can
  deadlock the component.
- Keep lock scopes small and never call unknown code while holding a lock.
  The C# compiler does not allow `await` directly in a `lock` body.
- For asynchronous mutual exclusion, await `SemaphoreSlim.WaitAsync`, then
  release in `finally`. A semaphore is not ownership-aware; every successful
  wait needs exactly one release.
- `Interlocked` makes one operation atomic. `volatile` controls visibility and
  some ordering; it does not make `value++` atomic.
- Publish immutable snapshots where possible. Immutability removes races only
  if the referenced object graph is also immutable.
- Document whether instance members, static members, enumeration, and disposal
  may be used concurrently. Thread safety is part of a public API contract.

A race that violates an invariant is **WRONG**. Choosing `lock` versus an
otherwise-correct channel or immutable design is usually **TASTE** until a
measured or semantic cost distinguishes them.
