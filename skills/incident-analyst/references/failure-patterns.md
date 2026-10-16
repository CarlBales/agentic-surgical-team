# Failure Patterns
Patterns generate discriminating questions; they do not diagnose an incident.
Use this catalog only alongside supplied evidence. When the order supplies its
own pattern notes or prior RCAs, those are the comparison corpus named in the
report; this file provides a generic vocabulary.
For every match record:
```text
Pattern: <name>
Matching signatures: <artifact IDs and labels>
Missing signatures: <expected but absent, with coverage caveat>
Contradictions: <artifact IDs>
Confounders: <other mechanisms with the same signal>
Evidence needed: <bounded export or signed read-only query>
Conclusion: OBSERVED fact | INFERRED mechanism | HYPOTHESIS to test
```
## Retry storm
Retries turn an initial failure or latency increase into additional offered
load. Multiple layers may multiply attempts.
**Signatures to seek**
- attempts per logical operation increase while logical demand is stable;
- repeated correlation/idempotency keys or explicit retry counters;
- traffic, queue depth, or dependency calls rise after error/latency begins;
- retry intervals align or show little jitter;
- timeouts exceed retry spacing, leaving old attempts in flight;
- recovery follows retry suppression, backoff, or upstream load reduction.
**Confounders and contradictions**
Traffic growth may be real users, replay, duplicate telemetry, or a batch job.
Flat attempts per operation weakens the pattern. Recovery after a dependency
fix does not show retries were an amplifier unless excess attempts are visible.
**Evidence request** — logical-operation IDs, attempt numbers, client/library
configuration, timeout/backoff values, and call-rate series for each layer.
The configuration alone is **OBSERVED**; a storm during this incident remains
**HYPOTHESIS** until attempts are connected to load.
## Thundering herd
Many workers wake or retry at once and contend for one resource after a common
event.
**Signatures to seek**
- synchronized spikes at expiry, reconnect, leader change, deploy, or recovery;
- many waiters awakened for one item or lock;
- periodic load at a shared timer or fixed backoff interval;
- contention, connection creation, or queue bursts without matching user load;
- phase alignment across otherwise independent workers.
**Confounders and contradictions**
A scheduled batch, autoscaling event, or coordinated client traffic can look
identical. Jittered event times and proportional demand weaken a shared-wakeup
claim.
**Evidence request** — per-worker timestamps with skew bounds, timer/lease
configuration, lock or connection waiters, and logical demand. Distinguish a
herd from the cache-stampede case below: a herd is synchronized activity; a
stampede specifically regenerates a missing/expired cached value.
## Cache stampede
Concurrent misses for the same hot key trigger duplicate origin work.
**Signatures to seek**
- hit ratio drops and origin load rises for the same key set;
- many fills or identical backend requests begin before the first completes;
- TTL expiry, eviction, invalidation, or cold start precedes the burst;
- hot-key concentration and similar request payloads;
- recovery after one value fills, request coalescing, or cache warming.
**Confounders and contradictions**
A broad cache outage, key-version change, genuine demand burst, or origin
slowdown can reduce hit ratio. Misses spread uniformly across unrelated keys
weaken a hot-key stampede.
**Evidence request** — key-hashed hit/miss/fill events, TTL and invalidation
history, origin requests, and coalescing/locking state. Do not request secret or
personal key values when stable hashes suffice.
## Certificate expiry or TLS trust failure
A certificate or trust artifact becomes invalid or unacceptable to a peer.
**Signatures to seek**
- handshake failures with an exact supplied reason and peer role;
- onset at `notAfter`, trust-store, revocation, chain, hostname, or clock
  boundary;
- only clients using a particular trust bundle or path fail;
- application requests never reach the server handler;
- rotation or trust-bundle correction restores handshakes.
**Confounders and contradictions**
Generic connection resets, DNS failures, protocol mismatch, cipher policy,
SNI routing, and clock skew can resemble expiry. A certificate visible from one
endpoint may differ behind another load balancer.
**Evidence request** — sanitized peer chain/metadata, exact handshake errors,
client and server times, SNI/hostname, trust-store version, endpoint path, and
rotation audit. Never invent a CVE or infer expiry from “TLS error.”
## DNS resolution or caching failure
Names resolve incorrectly, slowly, inconsistently, or not at all across the
resolver path.
**Signatures to seek**
- resolver errors, latency, or unexpected answer sets;
- failure varies by resolver, region, record type, or cached TTL state;
- authoritative change or expiry precedes propagation pattern;
- direct known-address tests succeed while name-based access fails, if a
  supplied safe diagnostic exists;
- negative caching or stale records persist for a TTL-shaped interval.
**Confounders and contradictions**
Connection, routing, proxy, service-discovery, and certificate failures can be
reported as name-related by clients. A current DNS lookup does not establish
the answer during the incident.
**Evidence request** — timestamped resolver/client logs, authoritative change
history, record type, TTL, resolver path, cache state, and historic answers.
Do not perform live queries without a signed source grant; request an export.
## Configuration push regression
A runtime or deployment configuration change alters behavior without changing
application code.
**Signatures to seek**
- audit record precedes impact after skew correction;
- affected population matches rollout target or config version;
- specific value has a mechanism for the observed failure;
- unaffected targets retain the old value;
- revert or corrected value aligns with recovery;
- validation accepted syntax but missed semantic interaction.
**Confounders and contradictions**
Deploys, traffic shifts, dependency events, and latent expiry can coincide with
a push. Presence of the new value on healthy targets weakens sufficiency but
may expose another required factor.
**Evidence request** — redacted diff, version/digest, target set, rollout and
revert audit, evaluation/precedence rules, and per-target effective value.
Never copy secret values into the RCA.
## Dependency outage or degradation
An upstream or downstream service fails, slows, returns bad data, or sheds
load, propagating impact through callers.
**Signatures to seek**
- caller errors/latency align with dependency attempts by correlation ID;
- dependency-side evidence shows matching failures or saturation;
- dependency-specific paths fail while independent paths remain healthy;
- circuit-breaker, fallback, timeout, or bulkhead transitions are visible;
- recovery ordering follows dependency recovery plus expected drain time.
**Confounders and contradictions**
Caller resource exhaustion can cause dependency timeouts while the dependency
is healthy. Network, DNS, credentials, and client-pool failures also appear as
“dependency unavailable.” Successful calls from equivalent clients contradict
a universal outage.
**Evidence request** — both sides' records, topology, call volume, latency
budget, timeout/fallback configuration, and affected path/population.
## Resource exhaustion
A finite resource reaches an effective limit: CPU, memory, disk, descriptors,
ports, threads, connections, queue slots, I/O bandwidth, quotas, or process
limits.
**Signatures to seek**
- resource level or waiters approach a documented/effective limit;
- allocation, admission, or scheduling failures name that resource;
- latency rises with contention and work queues;
- restarts, evictions, throttling, or garbage-collection changes follow;
- freeing or increasing the resource aligns with recovery.
**Confounders and contradictions**
High utilization can be a consequence rather than cause. Averages hide one
saturated shard or process. Missing telemetry from crashed instances creates
survivorship bias. A nominal limit may differ from an effective cgroup,
container, database, or quota limit.
**Evidence request** — per-instance usage and limits, queue/wait metrics,
allocation errors, restarts, topology, and demand. State units and aggregation.
## Deploy regression
A code or artifact release introduces behavior that causes the incident.
**Signatures to seek**
- impact begins within the rollout population after the new artifact arrives;
- old and new versions differ under comparable load/configuration;
- pinned diff contains a mechanism matching the symptom;
- rollback or isolation of the version aligns with recovery;
- canary or region sequence reproduces the impact pattern.
**Confounders and contradictions**
A deploy can restart caches, rotate connections, move traffic, or coincide with
config and dependency changes; the trigger may be deployment mechanics rather
than code. Healthy new-version instances and failing old-version instances
weaken a simple regression account.
**Evidence request** — artifact digest and revision, target/version timeline,
pinned diff, config parity, per-version outcomes, rollback details, and drain
lag. Never call the nearest deploy the root cause from time alone.
## Feature-flag misfire
A flag evaluates unexpectedly, targets the wrong population, exposes an
incompatible combination, or changes too quickly for dependent state.
**Signatures to seek**
- evaluation/audit records show changed result, rule, default, or targeting;
- impact population matches flag evaluation rather than deployment version;
- missing context or type coercion selects fallback behavior;
- two flags form an unsupported combination;
- disable/re-target aligns with recovery;
- clients cache flag state or receive it on different schedules.
**Confounders and contradictions**
A flag may only reveal a latent defect or shift traffic. Audit state at query
time may not equal evaluation state during the incident. Healthy affected
cohorts imply another factor or incomplete impact mapping.
**Evidence request** — versioned rules with sensitive values redacted,
evaluation events, defaults, context schema, cohort membership, client cache
behavior, and audit history.
## Cross-pattern feedback loops
Patterns combine. A deploy can cold-start a cache; misses overload a dependency;
timeouts trigger retries; retries exhaust connections; synchronized recovery
creates a herd. Do not choose one label and discard the chain.
Construct an ordered loop:
```text
initial condition -> changed load/state -> latency/error -> client response ->
additional load/state change -> saturation -> recovery or continued feedback
```
Each arrow needs evidence or remains a hypothesis. Identify the loop gain only
qualitatively unless supplied measurements support a number.
## Discriminating questions
When several patterns fit, ask what differs:
| Pair | Useful discriminator |
|---|---|
| retry storm vs real demand | attempts per logical operation and stable user demand |
| thundering herd vs scheduled batch | common wake trigger and worker phase alignment |
| cache stampede vs cache outage | hot-key duplicate fills versus broad unreachable cache |
| dependency outage vs caller exhaustion | dependency-side health and equivalent-client success |
| deploy vs config push | artifact population versus effective-config population |
| DNS vs network path | historic resolver answers/errors versus address-level path evidence |
| certificate vs clock error | chain validity against trusted time and peer-specific failures |
| resource cause vs symptom | contention preceding errors and response to freeing resource |
## Pitfalls characteristic of AI-generated pattern matching
- **Signature shopping.** Listing only matching signals. Always list missing
  signatures and contradictions.
- **Pattern as proof.** “Looks like a retry storm” remains **HYPOTHESIS** until
  logical operations and attempts are connected.
- **Generic invented logs.** Never claim an expected error string occurred;
  quote the supplied artifact.
- **Collapsed mechanisms.** Calling every synchronized spike a thundering herd
  or every miss burst a cache stampede.
- **Nearest-change bias.** Selecting deploy, flag, or config because its audit
  event is easy to see.
- **Single-layer view.** Blaming a dependency without checking caller pools,
  retries, DNS, certificates, and network path.
- **Remediation leap.** Recommending more retries, cache, or capacity before the
  mechanism is established. Hand options to the surgeon as bounded orders.
## Reporting a pattern match
A useful conclusion is narrow:
> **INFERRED:** Retries amplified the incident after 09:14 UTC. Observed
> attempt/logical-operation ratio rose from 1.0 to 3.7, dependency call rate
> rose while logical demand remained flat, and queue depth followed. The
> initial timeout mechanism remains **HYPOTHESIS** because dependency-side
> latency and caller pool waiters were not supplied.
This separates an established amplifier from an unresolved initiator and names
the evidence gap. That is stronger than declaring “root cause: retry storm.”
