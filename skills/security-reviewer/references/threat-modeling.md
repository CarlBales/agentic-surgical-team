# Change-Focused Threat Modeling

This procedure applies STRIDE to the delta between pinned `base` and `head`. It
is not a system-wide certification. Read it with
[the security reviewer skill](../SKILL.md).

The diff identifies changed assumptions. The files at `head` identify the actual
controls. The signed order and active decisions identify intended trust. A
generic threat list detached from those three is not evidence.

## Build the delta model

Write one sentence for each item before assigning threats:

1. **Security-relevant behavior changed.** What can a principal now do, send,
   read, store, authorize, or trigger that differed at `base`?
2. **Assets touched.** Credentials, identities, authorization state, money,
   source, execution capability, personal/payment data, audit records,
   availability, and integrity of persisted state.
3. **Entry points touched.** Routes, RPCs, queues, files, imports, webhooks, deep
   links, intents, WebViews, admin tools, scheduled jobs, build inputs, and CI.
4. **Principals.** Anonymous user, authenticated user, tenant member, operator,
   service identity, device app, third party, build worker, and attacker who has
   compromised one of them.
5. **Trust boundaries.** Browser/server, app/OS, service/service, tenant/tenant,
   process/database, repository/CI, CI/deployment, and trusted parser/untrusted
   bytes.
6. **State transition.** What durable or privileged state changes, and what
   precondition is supposed to authorize it?
7. **New dependency or authority.** Which library, service, token, platform
   permission, or configuration now has power it lacked before?

Do not assume a component is trusted because its name says `internal`. Establish
network reachability, caller identity, and enforcement at the receiving side.

## Draw only the necessary flow

A compact text flow is enough:

```
[principal] -- untrusted request --> (entry point)
             -- validated identity --> (policy decision)
             -- constrained data --> (interpreter or datastore)
             -- redacted result --> [principal]
```

Annotate each arrow with protocol, identity, integrity protection, and data
class. Mark a trust boundary where the enforcing authority changes. A function
call within one process may still cross a trust boundary when it passes from
untrusted parser output into a command, query, template, or deserializer.

A data-flow node is not a finding. Use it to ask whether the changed code creates
or removes an attack path.

## Apply STRIDE to each changed boundary

| Threat | Delta question | Typical evidence | Common mapping |
|---|---|---|---|
| **Spoofing** | Can a caller claim an identity, issuer, host, device, or callback it does not control? | token validation, signature checks, redirect/deep-link ownership | CWE-287; OWASP 2021 A07 |
| **Tampering** | Can untrusted input alter code, configuration, messages, packages, or durable state without integrity verification? | signatures, MACs, optimistic versions, lockfile integrity | CWE-345; OWASP 2021 A08 |
| **Repudiation** | Can a security-relevant action occur without attributable, integrity-protected evidence? | audit event at decision point, stable actor/action/result IDs | CWE-778; OWASP 2021 A09 |
| **Information disclosure** | Can data cross to a principal, log, client, tenant, or third party not entitled to it? | response fields, errors, logs, cache keys, export paths | CWE-200; OWASP 2021 A01/A02 |
| **Denial of service** | Can a bounded attacker force unbounded work, storage, fan-out, lock time, or retry? | limits, deadlines, queues, pagination, parser bounds | CWE-400; OWASP 2021 A04 |
| **Elevation of privilege** | Can a lower-privilege principal reach a function or object reserved for a higher one? | server-side policy before effect, tenant/object binding | CWE-269 or CWE-862; OWASP 2021 A01 |

The mapping must match the actual weakness. Verify the CWE entry; do not copy
this table mechanically into a report.

## Trace controls at the enforcement point

For each candidate path, answer:

- Where is identity established, and which fields are cryptographically bound?
- Where is authorization decided, against which resource and action?
- Can an attacker choose an object, tenant, path, URL, template, query fragment,
  command argument, or type discriminator after validation?
- Does validation occur before every side effect and on every alternate route?
- Is the result cached, and does the cache key include the security principal and
  all policy-relevant dimensions?
- What happens after timeout, retry, duplicate delivery, partial failure, or
  cancellation?
- Which data reaches logs, errors, metrics, analytics, backups, or clients?
- What limits CPU, memory, fan-out, body size, recursion, page count, and retry?
- Does the mitigation exist at `head`, and is it wired to this entry point?

A control in a helper or middleware file is not evidence by itself. Trace its
registration and ordering. Authentication after parsing an unbounded body, or
authorization after a write, is too late for those effects.

## Change-type prompts

### New route, RPC, webhook, or message handler

Identify caller authentication, replay protection where the protocol requires
it, object/function authorization, input bounds, idempotency, output fields,
error disclosure, and audit behavior. Check alternate methods and content types,
not merely the happy route.

### Schema, migration, or cache change

Ask whether rows become visible across tenants, old code can read the new shape,
backfill bypasses normal policy, caches omit a principal dimension, and rollback
re-exposes deleted or redacted data.

### CI, build, or dependency change

Map untrusted pull-request input to secrets and write-capable tokens. Check script
interpolation, executable downloads, integrity metadata, action/plugin pinning,
artifact provenance, and whether forked code executes in a privileged context.

### Browser change

Map origins, credentials, cookies, DOM insertion, navigation, framing, and
cross-window messages. CORS controls response sharing, not server-side
authorization. CSP limits impact; it does not make unsafe DOM construction safe.

### Mobile change

Map app/OS boundaries, exported components, deep links, local storage, backups,
screenshots, clipboard, logs, TLS policy, and WebViews. Treat WebView content as a
web origin with any exposed native bridge as privileged capability.

## Turn a path into a finding

A reportable security finding needs all of these:

1. Attacker prerequisite supported by the deployment or entry-point evidence.
2. Attacker-controlled action or input traced through `head`.
3. Missing, bypassed, or inadequate control at a named head location.
4. Security impact on a named asset or trust boundary.
5. Smallest repair at the correct enforcement point.
6. Verified CWE and OWASP mapping.

Then assign a judgment label and severity separately. The exploit sketch is one
line: “Authenticated tenant A member → supplies tenant B object ID → server
returns B record.” Do not write exploit payloads or test a live endpoint.

## Labeled examples

**WRONG — high — CWE-862 — OWASP 2021 A01.** A route authenticates the user
but fetches any account by request ID and never asks whether that user may read
it. Exploit: ordinary user → substitutes another account ID → reads protected
record. Fix: enforce action-and-object authorization server-side before fetch or
before response construction, according to the repository policy.

**WRONG — medium — CWE-400 — OWASP 2021 A04.** An unauthenticated import follows
continuation links with no page, byte, or deadline bound. Exploit: remote source
→ returns an endless chain → consumes worker capacity. Fix: impose explicit
signed limits and terminate with a visible failure.

**UNIDIOMATIC — low — CWE-778 — OWASP 2021 A09.** A new privileged action is
logged only in a general request line; actor and target can be reconstructed now
but future format changes can erase attribution. Exploit: privileged actor →
performs action → investigation requires ambiguous log correlation. Fix: emit a
structured audit event at the policy decision with non-secret actor, action,
target, and outcome identifiers.

**TASTE — low — CWE-693 — OWASP 2021 A05.** Two CSP constructions both constrain
the same script set and meet active policy. Exploit: no direct exploit
established. Fix: none; state the operational trade-off once.

## Severity discipline

Severity follows demonstrated exploitability and impact in this deployment, not
the weakness name. Account for required access, user interaction, default
configuration, blast radius, data sensitivity, detectability only when it
changes impact, and whether another independent control stops the path.

Do not assign a CVSS score unless the order supplies enough versioned system
context and explicitly requests it. A remembered calculator result is not
evidence. Do not increase severity merely because a pattern has public CVEs.

## Threat-modeling pitfalls in generated reviews

**Inventory presented as analysis. UNIDIOMATIC review practice.** Listing STRIDE
letters without a path gives the surgeon nothing to fix. Repair the review by
tracing one changed entry point to one asset through named controls.

**Middleware assumed active. WRONG review practice.** Generated code often
defines a credible policy but never registers it, or registers it after the
handler. Verify wiring and order at `head`.

**Universal “external attacker.” WRONG review practice.** A path may require a
tenant account, CI contributor rights, local device access, or an operator role.
State the real prerequisite; severity depends on it.

**Control-by-name. WRONG review practice.** A function called `sanitize`,
`verify`, or `secureStore` is not proof. Read its versioned behavior and its use
at the sink.

**System-wide claims from a narrow diff. WRONG review practice.** “The system is
secure” exceeds evidence. Report only the delta and list untouched boundaries as
out of scope.

**Speculative chain promoted to exploit. WRONG review practice.** If reachability,
configuration, or a downstream control is unknown, put the chain under
`Unverified` and name the exact evidence needed.
