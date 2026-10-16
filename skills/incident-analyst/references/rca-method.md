# RCA Method
A root-cause analysis is a learning artifact, not a verdict about a person.
Start from what the evidence can support. Prefer contributing factors over a
single root cause when several conditions were necessary.
Google's *Site Reliability Engineering*, chapter 15, “Postmortem Culture:
Learning from Failure” (2016), is the baseline practice:
<https://sre.google/sre-book/postmortem-culture/>.
## Define the incident frame
Before interpretation, write:
- incident identifier and systems in scope;
- analysis window and display time zone;
- user-visible failure or risk that defines impact;
- criterion for incident start, mitigation, recovery, and verification;
- evidence cutoff time;
- supplied sources and explicit exclusions;
- draft audience and requested output path.
Do not move the start to the first alert automatically. User impact may precede
an alert; a precursor may precede user impact without belonging in duration.
## Build the timeline in layers
Use a row per event:
```text
| Raw time | Normalized time / uncertainty | Event time or ingest time | Source | Event | Label | Relevance |
```
Build four layers, then interleave them:
1. **System change** — deploy, config or flag change, certificate rotation,
   scaling, dependency event, traffic shift, maintenance.
2. **System behavior** — saturation, queue growth, errors, retries, latency,
   restarts, health-state transitions.
3. **User impact** — failed, delayed, duplicated, stale, or incorrect work;
   affected population and duration.
4. **Response** — detection, page, investigation, hypothesis, intervention,
   recovery, and verification.
Every event keeps its source. If two clocks overlap after uncertainty is
applied, say “order unresolved” rather than imposing a sequence.
### Milestones to identify
- last known healthy evidence;
- earliest precursor supported by evidence;
- first supported user impact;
- first detectable signal;
- first actual detection;
- first responder acknowledgement, if supplied;
- hypothesis changes and why;
- mitigation start and completion;
- first recovery signal;
- sustained recovery and verification;
- follow-up effects after nominal recovery.
“First seen” means first in the supplied evidence, not necessarily first in the
system. Retention, sampling, and filters constrain that statement.
## Separate facts, reasoning, and hypotheses
Write observations before explanations.
**OBSERVED** — `gateway.log` records 503 at raw timestamp T with request ID R.
This says the record exists and attributes fields exactly as that artifact
defines them.
**INFERRED** — Requests failed downstream because the gateway record and the
service record share R, corrected time intervals overlap, and the gateway maps
that downstream failure to 503. State all three observations and the mapping.
**HYPOTHESIS** — Connection-pool exhaustion caused the downstream timeout.
Predict what should follow: high waiters, pool at limit, normal dependency
latency for acquired connections, and recovery after capacity becomes
available. Name evidence that would refute it.
Do not blend these into “pool exhaustion caused 503s” with one label.
## Develop competing hypotheses
For each plausible explanation, maintain:
| Field | Content |
|---|---|
| Hypothesis | one falsifiable mechanism |
| Explains | observations accounted for |
| Predicts | evidence expected if true |
| Contradicts | evidence inconsistent with it |
| Missing | smallest evidence needed |
| Status | retained, weakened, or refuted; never “proved” by fit alone |
Generate alternatives from different layers: application, dependency, data,
network, configuration, capacity, scheduler, client behavior, and
observability artifact. Do not create implausible alternatives merely to fill
a quota.
A leading hypothesis is the one best supported at the current evidence cutoff.
It remains **HYPOTHESIS** until the claim follows from observations. Likelihood
is not an evidence label.
## Build a causal account
A useful causal statement names a mechanism and a counterfactual:
> Because condition A changed mechanism B, outcome C followed; with guard D in
> place, A would not have produced C under the stated conditions.
Test each link:
1. Did the proposed factor precede the effect after clock uncertainty?
2. Is there a mechanism connecting them?
3. Does the effect vary with the factor where evidence permits comparison?
4. Does removal or reversal coincide with recovery, accounting for delays?
5. Are there cases where the factor exists without the effect, or the effect
   without the factor?
6. What alternative explains the same evidence with fewer unsupported steps?
Temporal proximity satisfies only the first question.
## Contributing-factor model
Organize factors without forcing one root:
- **Initiating condition** — change or event that began the failure path.
- **Trigger** — condition that activated a latent vulnerability.
- **Amplifier** — retries, fan-out, queueing, cache misses, or feedback that
  increased magnitude or duration.
- **Latent condition** — missing isolation, unsafe default, capacity margin,
  undocumented coupling, or control weakness already present.
- **Detection factor** — signal absent, threshold late, alert misrouted, or
  symptom-only monitoring.
- **Response factor** — ambiguous ownership, unavailable tooling, risky
  rollback, missing runbook, or evidence access delay.
- **Recovery factor** — what reduced impact, intentionally or otherwise.
A factor can occupy more than one category. Categories aid reading; evidence
still controls each claim.
## Limits of “five whys”
Repeated “why?” can expose a chain, but it has sharp limits:
- it encourages one linear path through a branching system;
- the stopping point is subjective;
- answers drift from mechanisms into judgment about people;
- the result depends on the first question and facilitator;
- it underrepresents feedback loops and interacting controls;
- “human error” becomes a stopping label rather than an explanation.
Use it only to probe a specific link. Build a factor graph and competing
hypotheses for the incident as a whole. Never stop at “operator mistake”; ask
what information, interface, safeguard, incentives, and recovery options made
the action locally reasonable.
## Swiss-cheese model
Reason's layered-defense model explains how several imperfect barriers can
align. Cite James Reason, “Human error: models and management,” *BMJ* 320
(2000): <https://www.bmj.com/content/320/7237/768>.
Use it to ask:
- Which preventive, detective, limiting, and recovery controls existed?
- Which were absent, bypassed, late, or coupled to the same failure?
- Which layer reduced harm despite the incident?
- Did apparently independent controls share configuration, dependency, or
  operator context?
Do not turn the model into a decorative diagram or assert every layer failed.
An incident can occur because no layer addressed the mechanism, and a layer
may have worked while still being insufficient.
## Blameless language
Blameless does not mean agency-free or vague. Describe actions and context
precisely without moral judgment.
| Avoid | Prefer |
|---|---|
| “The operator forgot to check the flag” | “The change path did not require or display the dependent flag state” |
| “A bad deploy broke production” | “Release R introduced behavior X; evidence E connects X to impact Y” |
| “They should have known” | “The available signal showed A; B became visible only after export C” |
| “Human error” | “Action A interacted with condition B; control C did not prevent or limit it” |
| “Obviously” / “simply” | the exact evidence and constraint |
Do not hide uncertainty behind passive voice. “Configuration changed” is
insufficient when an audit record can identify mechanism and time. Name a
person only when necessary to understand coordination, never to assign blame.
## Detection and response analysis
Distinguish:
- **detectable** — a reliable signal existed;
- **detected** — a person or automation noticed it;
- **diagnosed** — responders formed a supported explanation;
- **mitigated** — impact reduced;
- **resolved** — the failure mechanism ended;
- **verified** — sustained health and user outcome were checked.
Record which evidence moved responders between states. Assess alerts by
signal and timing, not whether an alert happened to exist. A noisy alert may
fire first and still be a red herring.
“What went well” requires evidence: a control limited scope, a rollback path
worked, an escalation brought needed context, or a dashboard shortened
analysis. Do not add ceremonial praise unsupported by the record.
## Pattern matching
When the order supplies prior RCAs or failure-pattern notes:
1. extract their diagnostic signatures and confounders;
2. compare each signature to this incident's evidence;
3. record matches, absences, and contradictions;
4. account for missing telemetry;
5. retain the match as **HYPOTHESIS** unless the incident evidence establishes
   the mechanism.
Never claim “same root cause” because graphs look similar. Patterns generate
questions; they do not supply facts.
## RCA draft structure
### Summary
Two or three sentences: user-visible event, duration/magnitude with evidence
boundary, strongest supported causal conclusion, and current uncertainty.
### Impact
Affected behavior and population, geographic or tenant scope if supplied,
duration, failed/delayed/duplicated work, data integrity, and confidence. Keep
internal error counts in a separate subsection unless they equal user impact.
### Timeline
Evidence-labeled table with raw/normalized time and uncertainty. Include change,
impact, detection, response, recovery, and verification milestones.
### Contributing factors
Mechanism-based factors with supporting observations, causal reasoning,
contradictions, and their role as initiator, amplifier, latent condition,
detection, response, or recovery factor.
### Detection
First detectable and detected points, alert behavior, signal gaps, and delay.
### Response
Actions, information available at the time, hypothesis changes, mitigation,
constraints, and verification. Separate observed effect from assumed effect.
### What went well
Controls and response actions shown to have limited impact or duration.
### Red herrings and contradictory evidence
Tempting correlations discounted, evidence against the leading hypothesis,
and implications for confidence.
### Open questions
One evidence gap per item: why it matters, exact bounded export or test, and
who should own the order.
### Recommended actions
Write candidate orders, not commitments:
```text
tester — Reproduce <mechanism> under <bounded conditions>, asserting <signal and user outcome>.
toolsmith — Add a reproducible read-only export for <fields/window> with query provenance and clock metadata.
reviewer — Review pinned change <range> for <specific failure mechanism>, reporting head-commit locations.
editor — Prepare the surgeon-accepted RCA draft for the named publication surface.
```
The surgeon chooses, prioritizes, and approves actions.
## Pitfalls characteristic of AI-generated RCAs
- **Narrative completion.** Filling missing events to make a smooth story.
  Preserve gaps and unresolved order.
- **Deploy monoculture.** Blaming the nearest release without mechanism,
  counterexamples, or rollback evidence.
- **Single-root pressure.** Compressing interacting factors into one cause
  because the document is called an RCA.
- **Metric arithmetic without definitions.** Converting rates, percentiles, or
  sampled counts into impact without query and denominator.
- **Decorative five whys.** Producing five sentences that end in “process
  failure” without testing causal links.
- **Action dumping.** Recommending “more monitoring,” “add retries,” or
  “improve tests” without an owner, mechanism, and observable acceptance.
- **Blameless vagueness.** Removing actors and sequence until nobody can learn
  what happened. Keep actions precise and judgments out.
- **Unsupported certainty.** Labeling the leading explanation **OBSERVED**.
  Mechanisms are usually inferred from several observed artifacts.
