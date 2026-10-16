# Incident Evidence Handling
Incident evidence is a set of partial measurements made by systems with
different clocks, sampling, retention, and failure modes. Preserve those
limitations. A precise timestamp on a log line is not the same as a precise
account of reality.
## Source register
Create this before building a timeline:
```text
| Source ID | Artifact/tool | Producer | Capture time | Event-time field | Query/filter | Sampling/aggregation | Retention/truncation | Clock notes | Integrity/provenance |
```
For files, record path, format, supplied checksum if any, and whether the file
is raw, transformed, redacted, or copied from another system. For a granted
read-only source, record the exact tool and operation, parameters, response
pagination, and invocation time.
A screenshot has provenance too: dashboard, panel title, displayed time zone,
window, legend, visible query if any, and capture time. It does not reveal
hidden transformations unless those are supplied.
## Evidence unit
Normalize each useful record without altering the original:
```text
Evidence ID: E-<n>
Source ID: S-<n>
Raw timestamp/value: <verbatim>
Parsed timestamp/value: <conversion and units>
Timestamp kind: event | emit | ingest | processing | capture | unknown
Entity/correlation: <request, trace, host, pod, job, deploy, ticket>
Claim supported: <narrow statement>
Label: OBSERVED | INFERRED | HYPOTHESIS
Limitations: <skew, sampling, truncation, ambiguity, redaction>
```
Quote only the minimum needed. Redact secrets and personal data consistently,
and state that redaction occurred. Do not alter identifiers needed for
correlation without a stable replacement.
## Timestamp kinds
- **Event time** — when the producer says the event occurred.
- **Emit time** — when the record was written by the producer.
- **Ingest time** — when the collection system received it.
- **Processing time** — when a pipeline transformed or indexed it.
- **Capture time** — when an export or screenshot was made.
- **Monotonic interval** — elapsed time measured on one process clock; useful
  for duration, not directly comparable across hosts.
- **Wall-clock time** — civil/UTC timestamp subject to synchronization,
  adjustment, time-zone parsing, and manual changes.
Never sort different fields together without naming the conversion. A late
batch can have old event time and new ingest time; a buffered logger can emit
records after a process recovers.
RFC 3339 defines a timestamp representation, not clock accuracy or event
semantics: <https://www.rfc-editor.org/rfc/rfc3339> (July 2002).
## Normalize without erasing uncertainty
For each source:
1. identify timestamp field and documented semantics;
2. parse explicit offset or zone; never assume local time silently;
3. retain raw text, fractional precision, and leap/invalid values;
4. convert to a chosen display zone, normally UTC;
5. estimate offset/skew only from supplied anchors;
6. attach an uncertainty interval;
7. sort only events whose intervals do not overlap;
8. note clock steps, restarts, or synchronization changes.
Represent an event as `[earliest, latest]`. If event A ends before event B
begins, A preceded B. If intervals overlap, order is unresolved.
### Skew anchors
Useful anchors include:
- the same correlation ID logged by two hosts;
- request send and receive records bounding a remote event;
- trace spans with documented clock correction;
- orchestrator event paired with process startup;
- database commit identifier observed by client and server;
- packet capture or load-balancer record with a trusted clock;
- explicit clock synchronization status supplied for the window.
A network round trip bounds offset only under stated latency assumptions. Do
not “correct” logs to make a hypothesis fit.
**OBSERVED** — two source records carry their raw timestamps.
**INFERRED** — source B was 3–5 seconds ahead based on repeated paired events
and bounded transit.
**HYPOTHESIS** — a 40-second ordering conflict is clock skew; synchronization
status or paired events would decide it.
## Logs
Logs can be absent because the event did not occur, the branch did not log, the
level was disabled, the process failed before flush, sampling dropped it,
rotation removed it, ingestion failed, or the export query excluded it.
Record:
- producer version and log schema;
- level threshold and dynamic changes;
- structured field types versus parsed text;
- buffering, flush, rotation, and retention;
- multiline and truncation behavior;
- sampling or deduplication;
- redaction and field removal;
- collector health and backpressure;
- query, index, time field, pagination, and result limit.
“Zero matching rows” is **OBSERVED** for the exact export/query. “No such event
occurred” is an inference requiring coverage of the relevant producer and
window.
Repeated lines may be retries, duplicate ingestion, replay, or one event logged
at several layers. Correlate attempt, request, trace, message, and producer
identities before counting.
## Metrics
A metric value is inseparable from definition and query. Record:
- instrument type: counter, gauge, histogram, summary, derived expression;
- unit and monotonicity;
- label filters and grouping;
- scrape/report interval and missing-series treatment;
- range and aggregation window;
- rate/increase function and reset handling;
- percentile source and whether aggregation is mathematically valid;
- downsampling, rollup, interpolation, and retention tier;
- panel transformations and alert evaluation delay.
Averages hide tails. Percentiles cannot generally be averaged across hosts or
windows. A counter reset can look like negative work or a recovery. A missing
series may become zero in one query and disappear in another.
**OBSERVED** — the supplied CSV contains values and labels.
**INFERRED** — user error rate rose, if numerator and denominator definitions
map to user requests and reset/missing behavior is accounted for.
**HYPOTHESIS** — exactly N users were affected from a sampled request metric;
request unsampled impact records or state the estimate method.
Preserve numerator, denominator, and uncertainty for every percentage.
## Traces
Record trace format/specification version, propagators, sampling decision,
head/tail sampling, dropped-span counts, clock correction, span kind, status
semantics, and attribute limits.
A trace can omit the root, errors, or slow requests because of sampling or
export failure. Parent-child structure records instrumentation relationships,
not necessarily causal ownership. Span status semantics depend on
instrumentation and specification version.
Use shared request or trace identifiers to correlate only after checking reuse,
truncation, and trust boundaries. A client-supplied ID can collide or be forged.
## Tickets, chat, and human recollection
These sources observe what participants knew and did, not necessarily system
state. Separate message creation time from referenced event time. Edits,
threading, deleted messages, copied timestamps, and retrospective summaries
matter.
A responder's contemporaneous hypothesis is **OBSERVED** as a statement they
made and **HYPOTHESIS** as an explanation of the system. Preserve both
meanings rather than treating the message as proof.
## Changes and deployment records
Record artifact digest, revision, environment, target set, rollout phase,
start/completion, health gate, rollback, configuration/flag state, and audit
provenance. “Deploy succeeded” often means an orchestrator completed, not that
all users received correct behavior.
A change before impact meets temporality, not mechanism. Look for:
- impact aligned with rollout population;
- version-correlated error or latency;
- mechanism visible in code/config and telemetry;
- reversal or isolation response;
- unaffected instances or regions as counterexamples;
- the same failure without the change.
## Correlation versus causation
Before writing “caused,” ask:
1. **Temporality** — did factor precede effect after skew bounds?
2. **Mechanism** — how can it produce this exact effect?
3. **Specificity** — does evidence localize the affected path or population?
4. **Covariation** — does effect change as factor changes?
5. **Intervention** — did removing factor alter effect, after delays?
6. **Counterexamples** — factor without effect or effect without factor?
7. **Common cause** — could a third event produce both signals?
8. **Measurement coupling** — could instrumentation create the correlation?
Not all questions can be answered. The label and `Unverified` section expose
which ones remain.
## Sampling and selection bias
- **Head sampling** can miss slow/error traces if selection happens early.
- **Tail sampling** can favor errors but lose data during collector overload.
- **Log sampling** distorts counts unless weights are known.
- **Top-N panels** hide affected low-volume entities and change membership.
- **Survivorship bias** shows healthy hosts that kept reporting while crashed
  hosts vanished.
- **Ticket bias** represents users who could and chose to report.
- **Query bias** follows filters chosen after a hypothesis formed.
- **Retention bias** leaves coarse metrics after detailed logs expire.
State the population the artifact represents. Never silently generalize from a
sample to all requests, users, or hosts.
## Red herrings and contradictory evidence
Maintain two explicit tables:
```text
| Candidate red herring | Why salient | Evidence against relevance | Remaining uncertainty |
| Contradiction | Claim weakened | Source/label | Alternative interpretation | Evidence to decide |
```
A red herring is not an event that “did nothing”; it is a tempting explanatory
lead not supported for the scoped incident. New evidence can restore it.
Seek contradictions deliberately:
- unaffected instances with the suspected condition;
- affected instances without it;
- timing that precedes the proposed cause;
- recovery before mitigation;
- flat resource metrics during a saturation claim;
- successful requests through the allegedly failed dependency;
- missing signature where telemetry coverage is known complete.
Do not bury contradictions in footnotes. They control confidence.
## Label promotion and demotion
Promote only when evidence changes:
- `HYPOTHESIS -> INFERRED`: observations plus a stated valid reasoning step now
  support the claim.
- `INFERRED -> OBSERVED`: only when a direct artifact shows the same narrow
  claim, not because more indirect evidence accumulated.
- Demote whenever provenance, clock, sampling, or semantic assumptions become
  uncertain.
An RCA conclusion is often **INFERRED** even when every underlying log line is
**OBSERVED**. That is correct.
## Evidence gaps and external access
For each gap specify:
```text
Question: <decision-relevant uncertainty>
Needed: <fields/signals and source>
Scope: <service/entities and exact time window>
Semantics: <event-time field, units, query, sampling, version>
Form: <read-only export preferred, or exact signed source operation>
Would confirm: <predicted pattern>
Would refute: <counter-pattern>
```
Without an exact `inputs.sources` grant, do not query a live system. If the
supplied exports cannot answer a required criterion, report `BLOCKED` with this
request rather than improvising another access path.
## Pitfalls characteristic of AI-generated evidence analysis
- **Synthetic detail.** Invented log messages, queries, event IDs, or exact
  times make a plausible but false RCA. Quote only supplied artifacts.
- **Timestamp laundering.** Converting all strings to UTC and dropping source,
  precision, skew, and timestamp kind creates false order.
- **Dashboard literalism.** Treating a rendered line as raw truth without its
  query, rollup, and missing-data behavior.
- **Absence certainty.** “No logs” becomes “did not happen” despite sampling,
  retention, or exporter failure.
- **Identifier overtrust.** Joining unrelated records on reused or
  client-controlled IDs without checking producer and scope.
- **Percentile arithmetic.** Averaging p99 values or converting sampled counts
  directly to users.
- **Confirmation filtering.** Requesting only evidence predicted by the lead
  and omitting disconfirming populations or windows.
- **Label inflation.** Calling a causal conclusion **OBSERVED** because its
  supporting events are observed.
