# Legacy Patterns and Hidden Behavior
A field guide to mechanisms that make source-level reading incomplete. Each
pattern states the evidence strength it can support and the next check that
prevents overclaiming.
## ASP.NET WebForms and VB.NET
### Page lifecycle and event wiring
**OBSERVED** — A page directive, control declaration, explicit delegate
subscription, or correctly named handler under `AutoEventWireup` establishes a
source-level event edge. Record the directive and handler `path:line`.
**INFERRED** — The handler executes for a request only after mapping the route,
page class, lifecycle stage, postback condition, validation, and any redirect
or exception before that stage. State that chain.
**HYPOTHESIS** — A method named `Page_Load` is active merely because of its
name. Confirm `AutoEventWireup`, base-class behavior, generated wiring, or a
runtime trace.
The order matters: initialization, state restoration, postback-data loading,
`Load`, control events, rendering, and unload can expose different values.
Code in `Page_Load` outside `If Not IsPostBack` repeats on postback. Record
whether validation occurs before the event and whether handlers inspect
`Page.IsValid`.
### ViewState, control state, and postback
ViewState can restore control properties between requests, while control state
preserves framework-required state even when ViewState is disabled. A hidden
field is untrusted input unless integrity protection is correctly configured
for the deployed version.
**OBSERVED** — Code reads or writes `ViewState("Key")`, a hidden field, or a
control property. Inventory the key, type conversion, default, and lifecycle
stage.
**INFERRED** — A value survives postback when state is enabled for the page and
control and no later data binding overwrites it. Cite each condition.
**HYPOTHESIS** — The database is queried only on the first request because the
UI “looks stateful.” Confirm the `IsPostBack` guard and data-binding calls.
Repeated `DataBind` during `Load` can replace posted selections before the
control event. Dynamic controls created after state restoration may lose
postback data. These are parity behaviors even when the rewrite avoids them.
### Session, application, and process state
- `Session` scope depends on configured session mode, timeout, cookie or URL
  identity, and serialization constraints for out-of-process modes.
- `Application` and `Shared`/static fields are process-level unless an
  external store intervenes. They do not imply cluster-wide consistency.
- `Global.asax` startup, session, authentication, error, and request hooks can
  mutate state or redirect before page code runs.
- Locking `Application` or a static object creates ordering and contention
  behavior. Record lock scope and exception release semantics.
**WRONG analytical move:** calling a static cache “global across servers.”
**HYPOTHESIS:** it is process-local unless deployment evidence shows one
process or an external coherence mechanism. The correction is to record the
scope supported by configuration.
### Configuration and transforms
`web.config` can inherit from machine and parent configuration, and deployment
transforms can replace or remove elements. App settings, connection strings,
HTTP modules/handlers, authentication, globalization, custom errors, session,
and compilation settings all alter behavior.
**OBSERVED** — A transform operation exists in a source artifact.
**INFERRED** — Its result governs the target only when the build/deployment
selection is supplied and the transformed output or process is known.
**HYPOTHESIS** — The filename implies the active environment.
Read `Option Strict`, `Option Explicit`, `Option Infer`, target framework, and
VB compilation settings. Late binding and implicit conversions can defer
errors or change overload selection. VB's `Nothing`, empty strings,
`DBNull.Value`, nullable values, and default value-type values are not one
state; inventory every conversion boundary.
### Culture, encoding, and numeric behavior
Formatting and parsing without an explicit culture use the current culture,
which can come from `globalization`, request selection, thread mutation, or the
host. Date parsing, decimal separators, casing, and string comparison can
therefore vary by request or environment.
**OBSERVED** — A parse or format call omits a culture argument.
**HYPOTHESIS** — It produces a particular text form. Confirm the current
culture at that point or characterize it under the deployed settings.
Record response encoding, request encoding, file encoding defaults, database
parameter types, decimal scale, midpoint rounding mode, integer overflow
settings, and whether empty form values become `Nothing`, `""`, zero, or
`DBNull`.
## Classic Java EE application servers
### Descriptors, annotations, and container services
The container can wrap code with routing, filters, authentication,
transactions, pooling, interception, retries, and lifecycle callbacks.
Reading the business method alone misses the contract.
**OBSERVED** — `web.xml`, EJB descriptors, annotations, or server binding
artifacts declare a mapping or service.
**INFERRED** — A request or invocation receives that service after resolving
spec version, metadata-complete settings, descriptor/annotation precedence,
and the deployed module.
**HYPOTHESIS** — An annotation is active because it is present in source.
Inspect servlet filters in declared order, listeners, error pages, security
constraints, welcome files, session settings, interceptors, startup beans,
timers, and message-driven beans. Include container callbacks such as
construction, injection, post-construct, pre-destroy, activation, and timeout.
### JNDI and environment bindings
A JNDI name is an indirection, not a resource identity. The same source name
can bind to different data sources, queues, URLs, or EJBs by environment.
**OBSERVED** — Code or a descriptor looks up a logical name.
**INFERRED** — It reaches a named resource only when a supplied server binding
maps that logical name to the target.
**HYPOTHESIS** — The lookup string reveals host, database, or destination.
Request the read-only naming export or deployed descriptor.
Record lookup scope, resource type, transaction enlistment, pooling, timeout,
credential source, and fallback. Never include credential values.
### EJB, transactions, and invocation boundaries
- Container-managed transaction attributes can begin, join, suspend, or omit
  a transaction around a method.
- A local self-invocation may bypass container interception that applies when
  another component calls through the proxy.
- Remote calls add serialization, pass-by-value, network failures, and
  retry/duplicate risks; local calls may preserve object identity.
- Exception type and declaration can affect rollback. Record the spec and
  deployment version rather than generalizing.
- Stateful beans, passivation, pools, and singleton concurrency controls
  create state and ordering not visible in method locals.
**INFERRED** — “The database write and message send commit together” requires
observations that both resources enlist in the same transaction and a stated
transaction boundary. A shared method body is not enough.
### JMS, timers, persistence, and class loading
Message delivery can be repeated. Capture acknowledgement/transaction mode,
redelivery metadata, dead-letter routing, selector, ordering assumptions, and
idempotency behavior. A timer may be persistent across restarts or recreated
at startup; distinguish configured behavior from source declaration.
Persistence providers can add lazy loading, cascades, flush-before-query,
dirty checking, optimistic locking, and generated SQL. A getter can therefore
cause I/O or fail outside a persistence context. Record mapping files,
annotations, provider/version, and transaction context.
Application-server class loading and shared libraries can select a different
library version from the packaged one. **HYPOTHESIS** — a bundled JAR is the
runtime implementation. Confirm class-loader policy or runtime inventory.
## Old PHP applications
### Request dispatch and includes
Web-server rewrites, a front controller, `include_path`, working directory,
autoloading, and prepend/append configuration decide which file runs.
Relative includes can resolve differently under web, CLI, and cron entry
points.
**OBSERVED** — A literal `require` creates a source dependency.
**INFERRED** — The file loaded at runtime follows only after resolving the
working directory and include path.
**HYPOTHESIS** — Every `.php` file is directly reachable. Start from routes,
server mappings, and command wrappers.
Include files may execute statements at load time, define globals, change
configuration, register shutdown handlers, or emit output before the apparent
entry function. Inventory those effects in order.
### Types, comparisons, arrays, and input
Historic PHP code often depends on implicit conversion. Loose comparison,
string-to-number conversion, truthiness, array key coercion, and arithmetic on
strings changed across PHP versions. Cite the exact deployed manual.
**OBSERVED** — Source uses `==`, implicit arithmetic, or untyped input.
**HYPOTHESIS** — A specific value compares equal without a version and exact
operands. Characterize boundary cases or consult the matching manual.
Distinguish missing keys, `null`, empty string, `false`, zero, and string
`"0"`. Record use of `isset`, `empty`, null coalescing, error suppression, and
notice/error configuration because they alter branches and visible failures.
PHP arrays preserve insertion order in supported modern versions but also
coerce some keys; old runtime behavior must be verified rather than projected.
### Sessions, globals, output, and configuration
- Superglobals are request inputs or environment views, not validated domain
  data. Record source and normalization.
- Sessions require startup and locking; default file-backed sessions can
  serialize concurrent requests for one session until the lock is released.
- `header` behavior depends on whether output has begun and on output
  buffering. Included whitespace can therefore change redirects or cookies.
- Process-level opcache and long-running workers violate the casual assumption
  that every request starts from fresh code/state.
- `php.ini`, per-directory settings, environment variables, and runtime
  `ini_set` calls form a precedence chain. Record which settings are mutable.
- Default timezone, locale, multibyte settings, error display, precision, and
  database-driver modes can all be externally visible.
Do not assume removed historical features were active merely because the code
is old. Establish runtime version and configuration.
## Stored procedures and database-side behavior
### Hidden write paths
Triggers, cascades, generated columns, defaults, sequences, materialized
objects, jobs, and audit mechanisms can turn one statement into many effects.
**OBSERVED** — A trigger definition names an event and body.
**INFERRED** — It fires for the application operation after resolving schema,
trigger enablement, operation type, and transaction context.
**HYPOTHESIS** — An audit row exists because a similarly named trigger is in
source. Request deployed schema or a supplied trace.
Trace nested triggers and routines far enough to identify all durable effects
and rollback boundaries. Record autonomous transactions or external calls if
the engine supports and the artifact uses them.
### NULL, conversion, ordering, and row counts
SQL NULL uses three-valued logic. Empty strings may or may not remain distinct
by engine. Implicit conversion can affect comparison, index use, errors, and
precision. Collation controls equality, order, accent, case, and sometimes
normalization behavior.
A result without an explicit `ORDER BY` has no contractual order. An
`ORDER BY` that is not unique leaves tie order unspecified. `TOP`/`LIMIT`,
window functions, cursor order, and “first row” logic must be read together.
Record decimal precision/scale at parameters, expressions, columns, and
client bindings; division and midpoint rounding can differ. Record time-zone
types, session zone, daylight handling, truncation, and client conversion.
Affected-row counts may include matched versus changed rows, trigger effects,
or driver-specific values. Treat them as behavior only with engine and driver
versions established.
### Session and transaction settings
Isolation level, autocommit, lock timeout, statement timeout, date format,
language, search path/default schema, quoted identifier mode, arithmetic
error settings, and ANSI compatibility switches can alter the same procedure.
A connection pool can retain session mutations between callers.
**INFERRED** — A routine is atomic when a transaction boundary and exception
rollback semantics cover every effect. `BEGIN` text alone does not prove the
caller cannot commit earlier or that external effects roll back.
Dynamic SQL adds unresolved object names, permissions context, quoting, plan
selection, and injection surfaces. Report constructed fragments and inputs;
do not invent the final statement when values are unavailable.
## Cross-stack implicit contracts
Inventory these even when they look accidental:
- stable output or processing order;
- duplicate suppression, retry, and idempotency keys;
- missing versus null versus empty versus zero;
- trimming, normalization, case folding, and collation;
- request, file, message, and database encoding;
- local time, UTC, offset preservation, and daylight transitions;
- decimal scale, integer overflow, midpoint rounding, and float tolerance;
- partial writes and notifications before failure;
- status-code, exception, and user-message mappings;
- cache freshness and stale fallback;
- process/session/global lifetime and cluster scope;
- permission checks performed by containers, descriptors, or database grants.
## Pitfalls characteristic of AI-generated analysis
- **Modernizing while describing.** Replacing loose comparison, lifecycle
  repetition, or trigger effects with the “sensible” behavior erases parity.
  Record first; recommendations belong elsewhere.
- **One-version memory.** Quoting current PHP, framework, or database rules for
  an older compatibility mode. Mark unverified until the version is known.
- **Container blindness.** Omitting filters, transactions, JNDI bindings,
  interceptors, or server libraries because they are outside the method body.
- **UI-only reasoning.** Assuming a hidden field, postback, or session value is
  trustworthy because the framework generated it. Record its actual
  validation and configuration.
- **Database as storage only.** Missing triggers, defaults, collation, session
  settings, and conversion behavior. Trace the deployed schema boundary.
- **Label inflation.** Calling conventional behavior **OBSERVED** without the
  artifact that shows it. Framework documentation supports a hypothesis until
  repository or runtime evidence connects it to this system.
