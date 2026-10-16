# C# and .NET Pitfalls

Recurring findings, especially in generated code. Labels depend on the
baseline and reachable behavior.

## Characteristic of generated C#

**Plausible nonexistent APIs.** A believable BCL method, wrong overload, or
extension from an unreferenced package is **WRONG**. Verify it in the versioned
API reference and target reference assemblies; use the available API, not a
shim named after the hallucination.

**Framework or package version drift.** Syntax exceeds `LangVersion`, an API
misses one TFM, or code remembers another package major. **WRONG.** Read every
TFM and the resolved package version, then use that version's official docs.
Do not add a guessed compatibility namespace or duplicate package.

**Invented analyzer IDs or severities.** A plausible `CA`/`CS` number, or a
real rule claimed as enabled without configuration, is **WRONG**. Confirm the
official entry and effective severity; otherwise omit the ID and mark output
unverified.

**Null-forgiving operators as repairs.** `value!.Member` performs no runtime
check. **WRONG** when null remains reachable; **UNIDIOMATIC** when an invariant
is real but hidden. Validate, branch, or fix the annotation.

**Blanket `ConfigureAwait(false)`.** **WRONG** where continuation needs UI or
request affinity; otherwise **UNIDIOMATIC** without a library convention.
Analyze each boundary rather than editing mechanically.

**`Task.Run` around async I/O.** It spends a worker on an operation already
asynchronous. **UNIDIOMATIC.** Await directly; reserve `Task.Run` for deliberate
CPU work or a documented blocking boundary.

**Fake verification.** Claimed build, test, format, or analyzer success without
output is a protocol violation. At L0 say `predicted`; at L1 quote results.

**Unnecessary abstraction or narration.** Layers with one local use are
**TASTE**, becoming **UNIDIOMATIC** when they obscure ownership or create a
public promise. Comments should explain invariants and version constraints,
not restate assignments.

## Async and task lifetime

**`async void` outside event handlers.** The caller cannot await completion or
observe failure. **WRONG.** Return `Task` or `Task<T>` and add `Async` to the
operation name. At a required event-handler boundary, catch expected failures
there and route them through the application's error policy.

**`.Result` or `.Wait()` on context-bound async work.** A UI or classic
ASP.NET thread blocks while the continuation needs that same context.
**WRONG.** Make the call chain async and await. Without a captured context it
may not deadlock, but still blocks and can starve server workers; describe the
actual failure rather than repeating folklore.

**`GetAwaiter().GetResult()` presented as a deadlock fix.** It changes exception
wrapping, not scheduling. **WRONG** if the blocking cycle remains. Remove the
sync-over-async boundary or isolate a genuinely unavoidable legacy boundary
with its constraints documented.

**Unobserved fire-and-forget work.** `_ = SendAsync()` drops completion,
exceptions, cancellation, and often a scoped service lifetime. **WRONG** when
work matters. Await it or hand it to an owned background queue/service that
observes failure and shutdown.

**Cancellation accepted but not propagated.** A method takes a token then
calls downstream async APIs without it. **WRONG** when the contract promises
cancellation. Pass the token and check it in CPU work. Do not substitute
`CancellationToken.None` to silence an overload choice.

**Disposing before async completion.** A stream, scope, response, or rented
buffer leaves its lifetime while a task still uses it. **WRONG.** Await inside
the ownership scope, or transfer ownership explicitly.

**Returning `ValueTask` by reflex.** Adds one-shot consumption constraints and
a larger public contract without evidence of saved allocations.
**UNIDIOMATIC.** Return `Task`; introduce `ValueTask` only after measurement and
with consumption documented.

## HTTP and I/O

**One `HttpClient` per request.** Repeated creation and disposal discards
connection pools and can exhaust sockets; long-lived handlers also need a DNS
refresh strategy. **UNIDIOMATIC**, and **WRONG** when it causes the stated
availability failure. Reuse a client with a suitable handler lifetime, or use
`IHttpClientFactory` when the application's Microsoft.Extensions stack owns
that facility. Do not add the factory package solely as a stylistic fix.

**Leaking `HttpResponseMessage` or response streams.** Can retain connections
and unmanaged resources. **WRONG** when the caller does not take ownership.
Dispose at the owning boundary, after content consumption, or document that
the returned object transfers disposal responsibility.

**Assuming one `ReadAsync` or `Read` fills a buffer.** Streams may return fewer
bytes than requested without reaching end-of-stream. **WRONG.** Loop until the
required length or EOF, or use a framework helper available on every target.

**Ignoring encoding.** `Encoding.Default`, implicit platform encodings, or
round-tripping arbitrary bytes through `string`. **WRONG** for portable
protocol data. Name the protocol encoding and specify invalid-byte behavior.

**Path concatenation with string separators.** Breaks on platform and edge
cases. **UNIDIOMATIC.** Use `Path.Combine` or another baseline-available path
API; still validate trust boundaries separately.

## Time

**`DateTime.Now` for persisted or compared timestamps.** Local time is
ambiguous across daylight-saving transitions and depends on machine zone.
**WRONG** when ordering, expiry, or cross-system exchange relies on it. Use
`DateTimeOffset.UtcNow` or a project time abstraction and store the offset/UTC
contract. `DateTime.Now` is fine for immediate local display, so do not flag
it mechanically.

**Wall-clock subtraction for elapsed duration.** Clock adjustment can move
backward or jump. **WRONG** when timeout or duration correctness matters. Use
`Stopwatch`; use `TimeProvider` only when the target framework supplies it and
testability is part of the design.

**Unspecified `DateTime.Kind`.** Serialization and conversion can reinterpret
a value. **WRONG** at a system boundary. Prefer `DateTimeOffset` or establish
and validate the `Kind` contract.

**Magic numeric time units.** `Delay(5000)` or `timeout = 30` hides whether the
unit is milliseconds or seconds. **UNIDIOMATIC.** Prefer `TimeSpan` and names
that expose units when an integer boundary is unavoidable.

## Strings, LINQ, and collections

**String concatenation in a loop.** Strings are immutable; repeated `result +=
piece` commonly reallocates and copies accumulated content. **UNIDIOMATIC** for
nontrivial loops, not automatically a correctness bug. Use `StringBuilder`,
`string.Join`, or direct streaming according to the shape, then measure if
performance is the claim.

**Culture-implicit parsing or formatting.** Results vary by current culture.
**WRONG** for protocols, persistence, identifiers, and machine-readable text.
Specify `CultureInfo.InvariantCulture` and an explicit format where the
contract is invariant. Current culture is correct for user-facing display.

**Ordinal identity compared linguistically.** Paths, tokens, protocol keys,
and identifiers have domain-specific comparison rules. **WRONG** when the
wrong comparer changes identity. Choose `StringComparison` or a collection
comparer explicitly; do not assume ordinal-ignore-case fits filesystem paths
on every platform.

**Multiple enumeration of `IEnumerable<T>`.** `Count()` then `foreach`, or
`Any()` then a second pass, may repeat I/O, database queries, expensive work,
or side effects. **WRONG** for one-shot/side-effecting sequences;
**UNIDIOMATIC** for needlessly expensive pure sequences. Enumerate once,
materialize once when bounded, or request a collection contract if repeated
access is required.

**Deferred LINQ over disposed state.** A method returns a query whose iterator
uses a disposed data context, reader, or stream. **WRONG.** Materialize within
the ownership scope or return an abstraction whose lifetime is explicit.

**LINQ for side effects.** `Select` builds a lazy projection; without
enumeration nothing happens, and forcing it obscures intent.
**UNIDIOMATIC** or **WRONG** if the effect never runs. Use `foreach`.

**Quadratic membership checks.** Calling `List<T>.Contains` inside a large
loop can produce O(n·m) work. **UNIDIOMATIC** when input sizes make the cost
material. Build a `HashSet<T>` with the correct comparer once; do not claim a
regression without sizes or measurement.

**Returning internal mutable collections.** Callers can violate invariants.
**WRONG** when mutation breaks the type's contract. Return a snapshot,
read-only wrapper, or explicit mutable collection according to intended
ownership.

## Exceptions and cleanup

**Swallowing `Exception`.** `catch (Exception) { }` converts failures and often
cancellation into false success. **WRONG.** Catch only what the boundary can
handle; add context and rethrow, or let it propagate.

**`throw ex;`.** Resets the visible stack origin. **WRONG** when preserving the
failure site matters. Use `throw;` inside the catch. When translating, include
the original as `InnerException`.

**Catch, log, and rethrow at every layer.** Produces duplicate logs without
adding recovery. **UNIDIOMATIC.** Log once at the boundary that decides the
outcome; add semantic context only where useful.

**Cleanup outside `finally`/`using`.** An exception skips disposal or lock
release. **WRONG.** Use `using`, `await using`, or `try/finally` with one clear
owner.

**Disposing injected dependencies.** The container or caller owns their
lifetime. **WRONG** when it causes later use-after-dispose. Dispose only objects
the component created or explicitly accepted ownership of.

## Equality and synchronization

**`Equals` without matching `GetHashCode`.** Equal objects can land in
different hash buckets, breaking `Dictionary` and `HashSet`. **WRONG.** Derive
both from the same immutable identity fields. Overloaded `==` should agree
with the documented equality semantics too.

**Mutable fields in hash identity.** Mutating a key after insertion makes it
unfindable in its current bucket. **WRONG.** Make identity immutable or do not
use the type as a hash key.

**Locking on `this`, `typeof(T)`, or a string.** External or unrelated code can
acquire the same monitor and deadlock the component. **WRONG** when exposure is
real; otherwise **UNIDIOMATIC**. Use a private readonly gate.

**Check-then-act on a concurrent collection.** Two individually thread-safe
calls do not make the sequence atomic. **WRONG** when races violate the
invariant. Use the collection's atomic operation or synchronize the compound
step.

**Using `volatile` for compound atomicity.** `volatile` does not make `count++`
atomic. **WRONG.** Use `Interlocked`, a lock, or redesign ownership.

## Legacy-to-modern migration hazards

**Treating `System.Web` as a package to replace.** Classic ASP.NET request,
configuration, module, handler, authentication, and synchronization-context
semantics do not map by namespace substitution to ASP.NET Core. **WRONG.** Map
each platform responsibility and ask the surgeon to decide the architecture.

**Changing only `TargetFramework`.** Legacy project imports, `packages.config`,
binding redirects, AppDomains, remoting, BinaryFormatter-era serialization,
Windows-only APIs, designers, and custom tasks may remain. **WRONG** when the
patch claims migration is complete. Inventory and verify each dependency.

**Assuming .NET Framework behavior in modern .NET.** Assembly loading,
configuration, current directory, globalization, networking defaults, and
ASP.NET context differ. **WRONG** when behavior relies on the old assumption.
Cite the specific runtime contract; do not use "modern .NET" as proof.

**Dropping binding redirects without resolving the graph.** Modern .NET uses a
different dependency model, but old plugins or retained .NET Framework targets
may still require redirects. **WRONG** if a supported target stops loading.
Inspect every target separately.

**Replacing synchronous APIs with fake async wrappers.** `Task.FromResult` over
blocking work preserves blocking; `Task.Run` changes scheduling and lifetime
but not the underlying API. **UNIDIOMATIC**, and **WRONG** if scalability or
cancellation is promised. Use a genuinely async API or document the legacy
boundary.

**Breaking VB.NET consumers silently.** Case-only names, non-CLS types, and
C#-specific call patterns can break a promised boundary. **WRONG.** Verify the
public metadata; VB implementation style remains outside this role.

**Trusting automated upgrade output.** Upgrade tools do not prove equivalent
behavior. **WRONG** when reported as completion; review and test the patch.
