# Secrets and Sensitive Data

This reference governs how the security reviewer handles evidence involving
credentials, personal data, payment-account data, logs, browser storage, and
mobile storage. Read it with [the security reviewer skill](../SKILL.md).

The first rule is containment: report enough to fix exposure without copying the
sensitive value into the report, chat, command line, scratch file, or external
service.

## When a possible secret appears

1. Stop expanding the value or reading adjacent secret material.
2. Record only pinned commit, path, line, and credential type, such as “private
   key material” or “database credential.” Never quote the value.
3. Determine from surrounding non-secret context whether it is an obvious inert
   placeholder, test fixture, public identifier, secret reference, or plausible
   credential. Do not test it.
4. Trace non-secret references to learn whether production code, CI, images,
   logs, or documentation consume it.
5. Report exposure and likely distribution paths. Credential validity and
   rotation are the surgeon's L3 actions.
6. If the guard blocks the path, quote the block and proceed without it. Never
   use another path, archive, encoding, process, or tool to recover the content.

A public key, account ID, client ID, or secret-store locator is not automatically
a secret. It can still be sensitive metadata. Classify by function and context,
not by an entropy score alone.

## Detection heuristics

High-confidence structural indicators include private-key headers, credential
assignment next to a provider or database client, signed bearer material,
password-bearing connection URLs, and CI variables expanded into commands or
artifacts. Report their type without reproducing any matching text.

Lower-confidence indicators include long random-looking strings, `password`,
`token`, or `secret` variable names, encoded blobs, test certificates, and sample
configuration. These require context. Entropy finds minified assets and hashes;
names find placeholders and public tokens. Neither proves a usable credential.

Trace these exposure surfaces in the diff:

- source, test fixtures, examples, generated files, and repository history in the
  pinned range;
- command arguments, process environment, exception text, debug output, and
  structured logs;
- CI interpolation, cache keys, artifacts, container layers, build metadata, and
  job summaries;
- URLs, query strings, headers copied into diagnostics, mobile deep links, and
  browser storage;
- configuration defaults that become active when a managed secret is absent.

At L0, do not run secret scanners. A scanner may write caches and may expand or
upload findings. Recommend an L1 `toolsmith` order for an approved offline tool,
or review a supplied scanner export. Never paste a candidate into a search
engine, breach service, provider API, or hash service.

## Labeled secret patterns

**WRONG — high — CWE-798 — OWASP 2021 A07.** A plausible production credential is
hard-coded in source and read by the active runtime path. Exploit: repository or
artifact reader → reuses embedded credential → reaches protected service. Fix:
replace it with a managed secret reference, remove distribution paths, and tell
the surgeon to assess rotation without printing the value.

**WRONG — high — CWE-532 — OWASP 2021 A09.** Request authorization material or a
password-bearing URL is logged. Exploit: log reader → obtains reusable credential
→ impersonates caller. Fix: omit the field or apply structured allowlist-based
redaction before serialization; do not rely on a later log sink.

**WRONG — medium to high — CWE-312 — OWASP 2021 A02.** A refresh token or private
key is persisted in plaintext where a lower-trust principal can read it. Fix:
avoid persistence when possible or use the platform's protected credential store
with access and backup policy appropriate to the threat model.

**UNIDIOMATIC — low — CWE-522 — OWASP 2021 A07.** A test-only credential is
clearly inert but resembles an operational secret and is copied across examples.
Exploit: no direct credential exploit established; developers may normalize an
unsafe pattern. Fix: use an unmistakable non-secret sentinel and state that
startup must reject it outside tests.

**TASTE — low — CWE-693 — OWASP 2021 A05.** Two secret-reference naming schemes
carry the same access and lifecycle semantics. Exploit: no direct exploit
established. Fix: none unless repository convention removes ambiguity.

## Logging hygiene

Prefer a positive list of fields safe to log. Redaction by key name misses nested,
renamed, encoded, or concatenated values and often runs after formatting.

Review every new log, error, metric label, trace attribute, audit event, crash
report, and analytics payload for:

- credentials, session IDs, authorization headers, cookies, signed URLs, and
  password-bearing connection strings;
- full request/response bodies, form fields, uploaded documents, and database
  records;
- direct identifiers and stable device/user identifiers;
- payment-account data or authentication data;
- stack traces and dependency errors that include configuration or URLs;
- unbounded attacker-controlled values that permit log forging or cost growth.

**WRONG — medium — CWE-117 — OWASP 2021 A09.** Attacker-controlled text is written
to line-oriented logs without structured encoding, allowing forged records.
Fix with structured logging that treats the value as data and bounds its length.

**UNIDIOMATIC — low — CWE-223 — OWASP 2021 A09.** A security event records a
message but omits non-secret actor, action, target, outcome, and correlation
identity, making incident reconstruction fragile. Fix at the decision point;
do not add sensitive payloads to compensate.

Logs need access limits, retention, deletion, and integrity appropriate to their
data. Logging more is not automatically safer.

## Map personal-data flow

For each changed data element, produce a compact map:

```
source -> validation -> purpose/use -> storage/cache -> response/log/analytics
       -> third party/region -> retention/deletion -> backup behavior
```

Ask:

- Is collection necessary for the signed purpose, or merely convenient?
- Is the field a direct identifier, quasi-identifier, sensitive attribute, or a
  linkable stable identifier?
- Which principal and tenant may read or alter it?
- Does a cache key, export, support tool, or analytics event widen access?
- Is transport protected at every boundary, including service-to-service?
- Does deletion cover replicas, indexes, derived records, and scheduled backups
  according to the stated contract?
- Can old and new binaries interpret redaction and deletion state consistently?
- Does test data contain copied production records?

Do not make legal conclusions about whether data is regulated. State observed
fields and flows, cite the project's classification policy when supplied, and
ask the surgeon for a decision where classification controls the verdict.

**WRONG — high — CWE-200 — OWASP 2021 A01.** A cache introduced by the change is
keyed only by object ID although access is tenant-scoped. Exploit: tenant A warms
shared key → tenant B requests same ID → receives A data. Fix by including every
policy dimension in the key or caching only below the authorization boundary.

**UNIDIOMATIC — low — CWE-359 — OWASP 2021 A04.** A new analytics event includes
a stable user identifier although aggregate behavior meets the stated purpose.
Exploit: analytics reader → links events to a person unnecessarily. Fix by omit,
aggregate, or use a purpose-limited pseudonymous identifier if policy permits.

## Payment-card data

Use PCI DSS **v4.0** only at high-level requirement areas unless the order
supplies an exact control interpretation. Relevant areas often include:

- Requirement 3: protect stored account data;
- Requirement 4: protect cardholder data with strong cryptography during
  transmission over open, public networks;
- Requirements 7 and 8: restrict access and identify/authenticate users;
- Requirement 10: log and monitor access;
- Requirement 11: test security of systems and processes;
- Requirement 12: support security with organizational policies and programs.

Do not claim PCI scope, compliance, or a failed sub-requirement from code alone.
Identify the account-data flow, storage, display, logging, access, and third
parties, then ask for the qualified compliance interpretation when needed.
Never include real card data in a report.

**WRONG — high — CWE-532 — OWASP 2021 A09; PCI DSS v4.0 Requirement 3/10 area.**
A payment request body is logged wholesale. Exploit: log reader → obtains account
data → unauthorized disclosure. Fix with a safe-field allowlist before logging
and verify historical retention separately through surgeon-controlled process.

## Session and token storage

### Web

For cookie-based sessions, review `Secure`, `HttpOnly`, `SameSite`, host/domain,
path, expiry, rotation, and CSRF together. Flags solve different threats.
JavaScript-readable browser storage exposes bearer tokens to any successful XSS;
a cookie can reduce script access but introduces CSRF considerations.

**WRONG — high — CWE-1004 — OWASP 2021 A07.** A bearer session cookie is readable
by script without a stated need. Exploit: injected same-origin script → reads
cookie → replays session. Fix with `HttpOnly` when the architecture permits and
repair the injection path independently.

Do not call `localStorage` always wrong: establish token value, origin threat,
lifetime, refresh behavior, and architecture. If required facts are absent, put
the conclusion under `Unverified`.

### Mobile

Use platform-protected credential storage for long-lived refresh material, with
accessibility, device-lock, backup, migration, and hardware-protection semantics
checked against the pinned OS version. Ordinary preferences, files, databases,
and logs are not credential stores merely because the app sandbox protects them.

Review screenshots, task switcher previews, clipboard, notifications, backups,
root/jailbreak assumptions, deep links, and WebView sharing. A platform API name
is not proof of its configuration; verify options in official versioned docs.

**WRONG — high — CWE-312 — OWASP MASVS 2.1.0 storage/auth areas.** A long-lived
refresh token is written to ordinary app preferences and included in backup.
Exploit: backup or lower-trust local reader → extracts token → renews access. Fix
with protected credential storage and explicit backup exclusion/lifecycle.

## Missing evidence

External configuration, historical logs, managed-secret metadata, advisory
status, and retention state require a surgeon-signed read-only source or supplied
export. If an order requires one and neither exists, report `BLOCKED`. Otherwise
state the limitation under `Unverified`. Never fill the gap by reading local key
files, invoking an unlisted provider operation, or testing a credential.

## Characteristic AI mistakes

**Example secret becomes fallback. WRONG.** Generated code often uses a polished
sample value when configuration is absent. Fix by failing closed and keeping
examples impossible to mistake for operational credentials.

**Redaction happens after interpolation. WRONG.** The secret is already in an
exception, metric, or command string before a sink filter sees it. Fix by never
constructing the sensitive representation.

**All fields logged for observability. WRONG.** Reflection or object spread turns
future fields into silent disclosures. Fix with an explicit safe-field schema.

**“Encrypted” without lifecycle. WRONG review practice.** Algorithm naming alone
says nothing about keys, nonces, access, rotation, or deletion. Move unsupported
claims to `Unverified` and ask for the exact construction and boundary.
