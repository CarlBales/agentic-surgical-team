# Excavation Procedure

A repeatable read-only method for recovering behavior from an inherited
system. The output is an evidence map, not a redesign proposal.

## Evidence discipline

Start a claim ledger before following code. Give every claim an identifier so
later contradictions update one place rather than creating two stories.

| Field | Record |
|---|---|
| Claim | one externally meaningful behavior |
| Label | `OBSERVED`, `INFERRED`, or `HYPOTHESIS` |
| Location | `path:line`, artifact identifier, or supplied record |
| Route | entry point and conditions that reach it |
| State | reads, writes, global/session state, transaction |
| Output | response, file, message, email, call, or visible error |
| Reasoning | only for `INFERRED`; observations and connecting step |
| Verification | only for `HYPOTHESIS`; evidence that would decide it |

Keep source evidence and runtime evidence distinct. A branch is
**OBSERVED** in source; taking that branch in production is not observed
without a trace, test result, or equivalent runtime artifact.

## Pass 0: bound the excavation

1. Restate the question as behaviors, not components: “what can submit an
   order?” is bounded; “explain the application” is not.
2. Record the exact revision or review SHAs and every path in and out of
   scope.
3. Register supplied artifacts: source, deployment bundles, configuration,
   schema, log exports, metrics, job schedules, and prior notes.
4. Record blind spots: generated code, binary libraries, unavailable server
   configuration, dynamic modules, encrypted settings, and inaccessible data.
5. Establish runtime versions from manifests or records. Syntax is weak
   evidence of runtime version because compatibility modes exist.
6. Identify the requested deliverables: inventory, flow, reachability,
   parity, or characterization candidates.

If the artifact needed to answer the core question is absent, stop with a
precise gap. Do not replace evidence with recollection of how the framework
usually behaves.

## Pass 1: recover the deployed surface

Read deployment wiring before implementation. Source trees contain unused,
historic, generated, and environment-specific branches.

| Stack | First deployment artifacts | Questions |
|---|---|---|
| ASP.NET WebForms | project files, `.aspx`, `Global.asax`, `web.config`, transforms, server mappings | Which pages, handlers, modules, startup hooks, and config variants are deployed? |
| Classic Java EE | archives, `web.xml`, `application.xml`, EJB descriptors, vendor descriptors, server naming exports | Which modules, context roots, filters, listeners, beans, destinations, and JNDI bindings are active? |
| PHP | web-server routes, front controller, `.htaccess`, `php.ini` export, include path, CLI/cron definitions | Which script receives each route, and which startup/include settings alter it? |
| Stored programs | schema definition, grants, synonyms, triggers, jobs, application call sites | Which routines are callable, scheduled, trigger-driven, or shadowed by another schema? |
| Batch/message | scheduler export, service definition, queue/topic binding, command wrapper | What starts it, with which identity, arguments, retries, and working directory? |

Descriptor declarations are **OBSERVED** configuration facts. Their deployment
in a specific environment is **INFERRED** unless the supplied artifact is the
actual deployed configuration or a runtime record confirms it.

## Pass 2: enumerate entry points

Build an entry-point table before tracing any one path.

### ASP.NET WebForms

- Map each `.aspx` directive to its code-behind or inline code and base class.
- Find page lifecycle handlers, explicit event subscriptions, and
  `AutoEventWireup`-named handlers such as `Page_Load`.
- Inspect `Global.asax` application, session, request, authentication, and
  error hooks.
- Include HTTP handlers/modules, route registration, web services, static
  page methods, callbacks, and scheduled executables outside the web app.
- Record postback controls and validation groups; a button event is an entry
  point conditioned on lifecycle and validation state.

### Classic Java EE

- Read servlet, filter, listener, security, and error-page mappings in
  descriptors and annotations. Record precedence at the deployed spec level.
- Find JAX-RS resources, EJB remote/local interfaces, message-driven beans,
  timers, startup singletons, and lifecycle callbacks.
- Map JMS destinations, connection factories, and JNDI names through supplied
  server bindings; a lookup string alone does not identify the target.
- Include interceptors and container callbacks because they can add
  transactions, authorization, retries, and side effects around business code.

### PHP

- Start from web-server rewrites and the front controller, not every `.php`
  file.
- Follow `include`, `require`, autoloaders, `auto_prepend_file`, and
  `auto_append_file`; record conditional and path-dependent includes.
- Include direct scripts, CLI dispatchers, cron wrappers, queue workers,
  upload endpoints, and framework route caches supplied with the order.
- Treat variable functions, reflection, and dynamic file names as unresolved
  edges until configuration or runtime evidence identifies them.

### Stored procedures and database behavior

- Enumerate application calls, granted executable routines, scheduled jobs,
  triggers, event handlers, and routines called by other routines.
- Record overload resolution, default parameters, synonyms/search paths, and
  session settings that select behavior.
- Add views, computed columns, constraints, cascades, and triggers as implicit
  steps around an apparent write.

## Pass 3: trace vertical slices

Trace one externally meaningful transaction at a time. Do not read a whole
layer and hope to reconstruct the route later.

For each slice:

1. Capture raw input and its source: HTTP field, header, message, file,
   environment variable, row, or procedure parameter.
2. Record decoding, trimming, defaulting, type conversion, validation, and
   normalization in execution order.
3. Follow branches, including authorization, empty-input, duplicate, timeout,
   and exception paths.
4. Record state reads and where consistency comes from: cache, session,
   singleton, transaction, lock, or optimistic version.
5. Expand every side-effecting call one boundary further: repository to SQL,
   mail facade to message creation, file helper to path and mode.
6. Stop at an external boundary and record request shape, timeout, retry,
   idempotency key, and response mapping when visible.
7. Record final output and intermediate effects that survive a later failure.

Use a value ledger for fields whose meaning changes:

| Step | Location | Representation | Null/empty rule | Locale/time/rounding |
|---|---|---|---|---|
| input | path:line | bytes/string/form value | missing differs from empty | request encoding |
| normalized | path:line | domain or primitive | default applied | culture used |
| persisted | path:line | column/parameter type | database nullability | scale/collation/zone |
| output | path:line | response/message/file | omission or sentinel | formatter/encoding |

## Pass 4: build the side-effect register

For every slice, inspect success, validation failure, exception, timeout,
retry, and cancellation paths.

| Effect | Capture |
|---|---|
| Database | operation, tables/routines, transaction owner, isolation clue, commit/rollback, trigger/cascade |
| File | path construction, working directory, encoding, overwrite/append, atomicity, cleanup |
| Message/email | destination, recipient selection, body/template, send timing, deduplication, retry |
| Network | endpoint selection, protocol, authentication source, timeout, retry, response mapping |
| Cache | key construction, scope, expiry, invalidation, stale behavior |
| Session/global | key or field, initialization, concurrency, lifetime, reset |
| Audit/log | event, level, identifier, redaction, whether failure suppresses it |

A call named `Save` is not evidence of persistence. Follow it to the boundary
or label the effect **HYPOTHESIS** with the missing implementation named.

## Pass 5: resolve configuration

For each behavior-bearing key, record:

1. default in code;
2. base configuration;
3. build-time transform, profile, or token substitution;
4. deployment/server override;
5. environment or command-line override;
6. runtime mutation or remote configuration, if supplied;
7. consumer and fallback when absent or malformed.

Preserve precedence as an ordered chain. Do not flatten environments into one
fictional configuration. Refer to secret keys and stores, never copy values.

Configuration can select types, SQL, endpoints, encodings, cultures, feature
branches, and error modes. Search for both literal keys and wrapper accessors.
Dynamic key construction remains a gap unless a supplied trace resolves it.

## Pass 6: map dependencies and state

Draw edges as `caller -> boundary -> selected target`, each with evidence.
Include libraries only when they alter observable behavior or create a hidden
runtime requirement. Distinguish:

- compile-time dependency from runtime plugin;
- local call from remote/container-mediated call;
- declared JNDI or connection name from its environment binding;
- code transaction from container or database transaction;
- request state from session, application, process, machine, and database
  state;
- source-controlled configuration from deployed configuration.

## Pass 7: classify reachability

Use an evidence ladder:

1. **OBSERVED live** — a supplied runtime trace, coverage record, request log,
   queue delivery, job history, or database audit reaches the path.
2. **INFERRED live** — an active route/descriptor and a complete static chain
   reach it under stated conditions.
3. **INFERRED unreachable** — control flow is impossible under the pinned
   build and configuration, with the contradiction cited.
4. **OBSERVED absent from deployment** — the deployed artifact inventory does
   not contain the module or entry point; this says nothing about other
   environments.
5. **HYPOTHESIS dead** — no references found, disabled feature, old naming, or
   apparent duplication without decisive deployment/runtime evidence.

Reflection, framework conventions, database triggers, generated callers,
external schedulers, and string-based dispatch defeat casual dead-code claims.
State `unknown` rather than collapsing them into dead.

## Inventory form

```text
Behavior B-<n>: <externally visible statement>
Label: OBSERVED | INFERRED | HYPOTHESIS
Entry: <path:line and route/trigger condition>
Inputs: <source, defaults, validation, null/empty rules>
Flow: <ordered path:line chain, including dynamic gaps>
State: <reads, writes, scope, transaction>
Outputs: <response/file/message/call/error>
Implicit contracts: <order, encoding, locale, zone, rounding, duplicate rule>
Dependencies/config: <selected edges and precedence>
Failure/retry behavior: <effects and result>
Evidence or reasoning: <artifact, or observations plus inference step>
Verification: <only when hypothetical>
```

## Pitfalls characteristic of AI-generated archaeology

- **Framework autopilot.** Claiming the documented lifecycle happened without
  checking mappings and overrides. Keep it **HYPOTHESIS** until artifacts tie
  the lifecycle to this entry point.
- **Search-result reachability.** Treating a caller found by text search as a
  live route. Record the call edge; prove the entry separately.
- **Name-based effects.** Reporting `Send`, `Commit`, or `Archive` by method
  name without opening its implementation. Follow to the boundary.
- **Configuration collapse.** Combining defaults and several transforms into
  one impossible environment. Preserve precedence per deployment target.
- **Happy-path inventory.** Omitting effects before an exception, retry, or
  rollback. Trace every exit that matters.
- **Confident dead-code claims.** Ignoring reflection, markup event wiring,
  naming services, triggers, cron, or external clients. Downgrade the label.
- **Invented compatibility facts.** Assuming current framework or database
  behavior for an old runtime. Cite the exact version or mark unverified.
- **Secret reproduction.** Copying connection strings or tokens into the
  report. Record the setting name, source, and behavioral consequence only.
