# Parity and Characterization
Comparison mode asks whether two implementations expose the same behavior.
Characterization captures what the legacy implementation does before anyone
decides whether that behavior is correct. Neither activity chooses the target
design.
Michael Feathers uses “characterization test” for a test that describes actual
behavior, often written to make change safer. Follow that discipline: observe
first, preserve selectively only after the surgeon decides.
## Preconditions for comparison
A meaningful comparison needs:
1. a pinned legacy revision or artifact;
2. a pinned rewrite revision or artifact;
3. bounded entry points and scenarios;
4. runtime and configuration baselines for both sides;
5. a list of observable channels;
6. explicit treatment of unknown external dependencies.
When the order supplies `inputs.review`, use the exact base and head SHAs in
the briefing. Read with `git diff <base>...<head>`,
`git log <base>..<head>`, and `git show <head>:<path>`. These L0 reads do not
prove runtime behavior. Do not compare a pinned legacy commit to a moving
working tree or branch name.
If the legacy and rewrite paths are in one revision, record that revision and
both roots. If generated artifacts or deployed configuration differ from
source, list them separately.
## Build independent inventories first
Do not read a rewrite and then search only for matching legacy code. That
creates confirmation bias and misses behaviors implemented through different
mechanisms.
1. Inventory legacy entry points, scenarios, side effects, and contracts.
2. Inventory rewrite entry points, scenarios, side effects, and contracts.
3. Normalize behavior names only after both lists exist.
4. Join the lists into the parity table.
5. Preserve one-sided behaviors as rows; absence is a result, not noise.
A source construct is not the comparison unit. “Uses a session” and “uses a
signed token” may implement the same visible continuity contract, while two
methods with the same name may differ in validation, ordering, or failure.
## Behavior dimensions
For every externally meaningful operation compare:
- route, trigger, schedule, and preconditions;
- accepted inputs and normalization;
- authorization and validation order;
- missing, null, empty, zero, and duplicate semantics;
- output fields, status, headers, messages, files, and ordering;
- database writes, triggers, audit, cache, queues, email, and external calls;
- transaction, retry, timeout, cancellation, and idempotency behavior;
- exception-to-output mapping and partial effects on failure;
- locale, collation, case, encoding, time zone, and daylight behavior;
- numeric precision, scale, rounding, overflow, and float comparison;
- state scope and lifetime: request, session, process, cluster, database;
- configuration defaults, precedence, and feature-state behavior;
- observability that downstream operators or integrations rely on.
Do not omit an undesirable dimension. A defect can be an observed compatibility
constraint until the surgeon explicitly rejects it.
## Parity table
Use one row per behavior, not one row per file or endpoint.
```text
| ID | Scenario / behavior | Legacy | Rewrite | Status | Evidence label | Evidence / reasoning | Consequence | Test candidate |
|---|---|---|---|---|---|---|---|---|
| B-01 | empty customer ID | returns validation message; no write | writes row with generated ID | DIVERGENT | OBSERVED | legacy path:line; rewrite path:line | externally visible and durable | tester: characterize empty/missing IDs across both paths |
```
Allowed status values:
| Status | Meaning |
|---|---|
| `PRESENT` | Both sides implement materially equivalent behavior under the stated baseline |
| `ABSENT` | A behavior exists on one side and no corresponding behavior is found on the other at the available evidence strength |
| `DIVERGENT` | Both address the scenario but differ in input, output, side effect, ordering, failure, or contract |
| `UNVERIFIED` | Evidence cannot decide parity without execution, configuration, or external access |
`PRESENT` is not “both contain similar code.” State the evidence chain for
equivalence. `ABSENT` from static search is usually **HYPOTHESIS** unless the
complete dispatch/deployment surface makes absence decidable.
## Applying evidence labels to parity
**OBSERVED** parity requires direct artifacts for both compared facts. Source
can directly show constants, mappings, branch bodies, and called boundaries;
a supplied characterization result can directly show runtime outcomes.
**INFERRED** parity requires observations from both sides and the connecting
reasoning. Example: both normalize to a documented database routine with the
same supplied configuration and neither transforms the result afterward.
**HYPOTHESIS** covers likely equivalence or divergence that depends on an
unresolved version, dynamic target, environment binding, data distribution,
or execution path. It must name the evidence that would confirm or refute it.
The parity row's evidence label grades the weakest material claim in the row.
Do not hide a hypothetical rewrite edge behind an observed legacy result.
## Characterization candidates
A strong candidate has five parts:
1. **Boundary** — callable seam or observation point.
2. **Fixture** — exact input and relevant initial state.
3. **Observation** — output and all durable or externally visible effects.
4. **Control** — clock, random seed, environment, locale, configuration, and
   external dependency behavior.
5. **Purpose** — the behavior or parity uncertainty it resolves.
Candidate form:
```text
Candidate C-<n>
Behavior: <inventory/parity ID>
Fixture: <input and initial state>
Exercise: <entry point, not internal implementation>
Observe: <return/response plus writes, messages, files, calls, ordering>
Control: <clock, locale, zone, random, configuration, doubles>
Expected source: OBSERVED artifact | golden-master capture needed
Risk: <why this behavior matters>
Recommended order: tester — Characterize <behavior> at <boundary> with <fixture>, asserting <observation> under <controls>.
```
The archaeologist recommends this order. The tester designs and implements the
test and decides suitable harness mechanics within its order.
## Selecting candidates
Prioritize behavior that is:
- exercised by important entry points;
- implicit rather than declared;
- costly or irreversible as a side effect;
- dependent on locale, time, order, concurrency, or database settings;
- divergent or unverified in the parity table;
- behind a difficult seam or unavailable dependency;
- coupled to retries, duplicate delivery, or partial failure;
- relied on by an external consumer.
Do not characterize every line. Characterize boundaries and decisions that can
change visible results.
## Working at seams
A seam is a place where behavior can be changed or observed without editing the
core logic. Identify seams; do not introduce them unless an implementation
order assigns that work.
Common existing seams:
- public HTTP, message, CLI, file, or procedure boundaries;
- repository, gateway, mail, clock, and configuration interfaces;
- virtual or overridable methods in inherited code;
- link-time or class-loader substitution supported by the stack;
- database transaction rollback around a test fixture;
- captured filesystem, queue, or network adapters;
- process boundary with recorded requests and responses.
**INFERRED** — a seam appears usable when call sites route through it and the
test harness can substitute it under the pinned runtime. **HYPOTHESIS** — a
class or method is substitutable based only on its name or visibility.
If no seam exists, recommend a separate surgeon decision or implementation
order. Do not smuggle production refactoring into a tester order.
## Golden-master and snapshot use
A golden master is useful when output is large and poorly understood, but it
can freeze noise and secrets as easily as behavior.
Before recommending capture:
- enumerate nondeterministic fields and choose normalization rules;
- separate semantic order from incidental map or query order;
- redact secrets and personal data without erasing relevant distinctions;
- capture side effects as well as response text;
- use representative and boundary fixtures, not one production sample;
- store provenance: revision, runtime, configuration, and capture command;
- require human review of the first baseline.
Never recommend “approve whatever the legacy emits.” The initial capture is
evidence for surgeon review, not an oracle by default.
## Stack-specific observation points
### WebForms
Exercise the page or handler boundary when possible. Observe response, redirect,
validation text, ViewState-relevant continuity, session mutation, database
writes, and mail/message calls. Control culture, time zone, authenticated user,
postback fields, and configuration.
### Classic Java EE
Exercise the external servlet/resource, EJB proxy, message destination, or
timer seam rather than direct construction that bypasses the container.
Observe transaction outcome, interceptor/security effects, messages, database
writes, redelivery, and serialization. Pin container/spec and server bindings.
### PHP
Exercise the actual front controller, direct script, CLI, or worker wrapper.
Control `php.ini` settings, include path, working directory, session storage,
timezone, locale, and database-driver modes. Capture headers before body and
warnings/errors separately.
### Stored procedures
Call through a transactionally isolated fixture when the engine permits it.
Observe result sets, output parameters, row counts, all table changes,
trigger/audit effects, errors, and sequence consumption. Pin schema, session
settings, collation, driver, and engine version. A rollback may not reverse
sequence allocation or external effects; verify rather than assume.
## Nondeterminism and hidden inputs
Treat these as input dimensions:
- wall clock, monotonic clock, time zone, and daylight rules;
- random values, generated IDs, and sequence state;
- hash/map iteration and database tie order;
- concurrency, lock acquisition, and message scheduling;
- process and session residue;
- filesystem order and working directory;
- remote service retries, timeouts, and changing data;
- locale, collation, encoding, and Unicode normalization.
Normalize only fields proved irrelevant. Otherwise assert relationships, such
as “timestamp lies between start and end,” or control the source.
## Recommended one-line orders
Use actionable, bounded handoffs:
- `tester — Characterize null, empty, and missing account IDs at the legacy HTTP boundary, asserting status, body, writes, and mail calls under the deployed locale.`
- `tester — Compare legacy and rewrite ordering for tied timestamps using the same fixture and database collation, recording the complete returned ID sequence.`
- `tester — Characterize duplicate message delivery at the consumer boundary, asserting database, audit, and outbound-message effects after two deliveries.`
- `toolsmith — Provide an L1 reproducible harness for the pinned legacy runtime and configuration without changing production behavior.`
Do not write “add tests.” Name the uncertainty and observation that closes it.
## Pitfalls characteristic of AI-generated characterization
- **Asserting the rewrite's intended result against legacy.** This tests the
  design, not actual behavior. Derive expectations from observed artifacts or
  an explicitly reviewed capture.
- **Mocking away the contract.** A direct method test can bypass container,
  trigger, session, encoding, or transaction behavior. Exercise the nearest
  meaningful boundary.
- **Snapshotting noise.** Uncontrolled timestamps, IDs, hash order, and paths
  create false divergence. Control them or assert stable relationships.
- **Response-only parity.** Equal JSON with different durable writes, emails,
  retries, or ordering is not parity.
- **One happy fixture.** It misses null/empty, boundaries, failures, duplicate
  delivery, and locale/time cases where legacy contracts hide.
- **Calling absence proof.** No matching search result is not proof that
  behavior is absent under reflection, configuration, or database triggers.
- **Turning tests into policy.** A characterization candidate records behavior;
  only the surgeon decides whether acceptance criteria should preserve it.
## Completion check
A comparison is ready for the surgeon when every scoped behavior has a parity
row, every row has one evidence label, every divergence states the exact axis,
contradictory evidence is visible, and every unresolved high-risk row has a
bounded tester order or a named missing artifact. “Mostly equivalent” is not a
verdict without that table.
