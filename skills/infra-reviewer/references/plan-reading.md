# Reading Terraform and OpenTofu Plans

A plan is evidence of proposed actions for one configuration, variable set,
provider selection, state snapshot, and refresh result. It is not a deployment
result and it is not proof of live state. Read the artifact before reviewing
configuration intent.

Authoritative formats are the Terraform
[JSON output format](https://developer.hashicorp.com/terraform/internals/json-format)
and the matching OpenTofu documentation for the producing version. The JSON
format has its own `format_version`; do not treat that as the CLI version.

## Evidence boundary

Accept a plan only from the work order's `inputs.files` or an explicitly
allowed read-only `inputs.sources` tool. Record:

- artifact path and hash if supplied;
- JSON versus human-readable text;
- `terraform_version` or OpenTofu producer version;
- `format_version` for JSON;
- reviewed commit, variable set, workspace, account, and region when present;
- whether refresh was enabled, only if provenance says so;
- timestamp or staleness information when present.

If the order asks what a plan does but supplies none, report `BLOCKED`. Source
configuration cannot prove provider-planned actions, unknown values, live
drift, or replacement behavior.

Treat every saved plan and `terraform show -json` export as secret-bearing.
Sensitive values can be present in clear text even when sensitivity masks mark
them for redaction in normal UI. Never paste a credential into a finding.
Name the path and describe the class of value instead.

## Orienting in JSON

Read top-level fields in this order; fields vary by producer version, so check
the versioned format documentation before treating absence as meaningful.

| Field | Review use |
|---|---|
| `format_version` | Select the schema documentation; reject an unsupported major format rather than guessing |
| `terraform_version` | Tie behavior and provider protocol expectations to the producing CLI |
| `variables` | Identify supplied root variables; redact sensitive values |
| `resource_changes` | Primary proposed actions for managed resources and data resources |
| `resource_drift` | Changes found during refresh when the producer emits them; not changes caused by configuration |
| `output_changes` | Added, changed, removed, unknown, and sensitive root outputs |
| `planned_values` | Proposed value tree after applying known changes |
| `prior_state` | State snapshot used for comparison, not guaranteed current now |
| `configuration` | Parsed configuration representation useful for expressions and references |

Do not infer an empty live environment from an empty or omitted field. First
establish what the producing version emits and what command produced the file.

## Resource-change anatomy

For each entry in `resource_changes`, capture:

- `address`, including module path and instance key;
- `mode` (`managed` or `data`) and resource `type`;
- `provider_name` when present;
- `previous_address` when a move is represented;
- `change.actions`;
- `change.before`, `change.after`, and `change.after_unknown`;
- `change.before_sensitive` and `change.after_sensitive`;
- `change.replace_paths` for replacements.

The `actions` array is a small ordered vocabulary:

| Actions | Meaning |
|---|---|
| `["no-op"]` | no proposed change |
| `["create"]` | create an object |
| `["read"]` | read a data resource during apply or refresh |
| `["update"]` | update in place |
| `["delete"]` | destroy an object |
| `["delete", "create"]` | replace by destroying first, then creating |
| `["create", "delete"]` | replace by creating first, then destroying |

Do not collapse both replacement orders into “recreate.” Destroy-first adds an
outage/data-loss window. Create-first can hit quotas, name uniqueness, IP
allocation, attachment, or double-running costs. The ordering is proposed,
not proof that apply will complete in that order without failure.

`replace_paths` contains attribute/index paths that contributed to replacement.
Translate each path against `before` and `after`; do not claim a path “forces
replacement” unless the artifact shows it or the exact provider-version docs
say so. More than one path may contribute.

`after_unknown` is a shape mask. A true leaf means the final value is not known
until apply. Absence from `after` is not the same as null or deletion when the
unknown mask covers it. Report unknown identity, address, policy, endpoint, or
count values under `Unverified` if they affect risk.

Sensitivity masks are also shape masks. Use them to avoid disclosure, not to
skip review. A newly sensitive output may still leak through logs, downstream
systems, resource identifiers, or an unprotected state backend.

## Reconcile the blast radius

Build an inventory before writing findings:

| Class | Count | Addresses | High-consequence notes |
|---|---:|---|---|
| create | | | public endpoints, identities, keys, stateful services |
| update in place | | | policy, routing, encryption, retention, size |
| replace create-first | | | quota, duplicate traffic, naming |
| replace destroy-first | | | outage, data loss, dependency gap |
| destroy | | | retained data, dependents, recovery |
| move | | | old/new address and whether behavior is unchanged |
| data read | | | apply-time unknowns and external dependencies |
| drift | | | observed state/configuration discrepancy |

Expand modules. A one-line module version change can alter dozens of resource
instances. Group repeated homogeneous instances, but name every stateful,
public, identity, network-edge, encryption, or cross-account resource.

For each stateful replacement—database, bucket/object store, disk/volume,
queue/topic with retention, key, cluster, or durable identity—find an explicit
surgeon decision covering replacement and migration/recovery. Without one,
report **WRONG**. A snapshot default or provider retention setting is not a
migration decision.

For destroys, ask:

1. Is the address intentionally removed, or was it renamed without a move?
2. Does the service retain data after deletion, and is that configured here?
3. What consumes its ID, endpoint, key, policy, or data?
4. Is the destroy caused by count/`for_each` key instability?
5. Does the order contain the irreversible-action decision?

## Reading human-readable plans

Text plans are less machine-reconcilable but still useful. Preserve the legend
from the artifact. Common Terraform symbols are:

| Symbol | Meaning |
|---|---|
| `+` | create |
| `~` | update in place |
| `-` | destroy |
| `-/+` | destroy, then create replacement |
| `+/-` | create, then destroy replacement |
| `<=` | read a data source |

Text may annotate an attribute with “forces replacement.” Quote that annotation
and location; do not generalize it to other provider versions. `(known after
apply)` is unknown, not a safe value. “Sensitive value” is deliberately
redacted and must not be reconstructed.

Check the summary counts against the body. Then compare the body to changed
configuration: every material changed resource should have an explained plan
outcome, and every surprising plan action should have an originating change,
drift entry, provider upgrade, variable difference, or explicit unknown.

## Drift, moves, and imports

`resource_drift`, when present, records refresh differences. Keep it separate
from proposed configuration changes. Drift can make a safe-looking diff
high-risk, but a plan does not explain who caused it or when.

A `previous_address` or an explicit moved block can preserve object identity
across refactoring. A delete/create pair after an address rename often means the
move is missing. Report **WRONG** for an unapproved stateful recreation;
recommend a declared move or a surgeon-controlled state operation after exact
version and address verification.

Never run import or state commands. If an object must be adopted or moved,
state the old/new addresses and have the surgeon execute the reviewed command
under an explicit decision.

## Finding examples

**WRONG — unapproved database replacement.**
`module.data.aws_db_instance.primary` has actions `["delete","create"]` and
`replace_paths` names an identifier path. No decision covers migration or
replacement. Minimal fix: preserve identity or obtain an explicit migration,
backup, outage, and rollback decision before apply.

**WRONG — unknown public exposure.** A security-group rule is created with an
apply-time-unknown CIDR and no constraint visible in configuration. The plan
cannot establish bounded ingress. Minimal fix: derive the rule from an approved
bounded prefix or supply evidence resolving the unknown before acceptance.

**UNIDIOMATIC — opaque module churn.** A module ref moves to a new immutable
version and changes many low-risk tags, but the report gives no grouped
inventory. The plan can work; the operational cost is hidden review scope.
Minimal fix: summarize homogeneous tag-only updates separately from behavior.

**TASTE — ordering equivalent tag updates.** The same non-functional tag map is
rendered in a different stable order with no provider/state effect. Mention
once only if it obstructs review.

## Characteristic AI mistakes

- Declaring “no destructive changes” after reading only configuration, not the
  plan. **WRONG.** Require and reconcile the plan.
- Treating `["create","delete"]` as no-downtime. **WRONG.** Capacity, naming,
  health checks, and dependency cutover remain unverified.
- Inventing a force-replacement attribute from memory. **WRONG.** Use
  `replace_paths` or exact provider-version documentation.
- Copying full `before`/`after` objects into a report. **WRONG** when they hold
  secrets; otherwise noisy. Quote only risk-bearing, redacted paths.
- Calling every unknown value dangerous. **UNIDIOMATIC.** Explain the specific
  decision the unknown prevents.
- Treating plan counts as blast radius. **UNIDIOMATIC.** Consequence depends on
  resource kind, identity, state, reachability, and dependencies.
- Claiming a supplied plan is fresh or matches `head` without provenance.
  **WRONG.** Put the linkage under `Unverified`.

## Plan-review output

A useful plan finding names:

1. resource address and head configuration location;
2. exact action array or text symbol;
3. risk-bearing before/after path, redacted;
4. replacement path and order when applicable;
5. dependency, state, identity, or exposure consequence;
6. explicit decision found or missing;
7. smallest configuration correction or surgeon question;
8. producer/provider documentation version;
9. anything needing live state, credentials, or apply under `Unverified`.

A sound verdict means the supplied artifact has no required fixes within the
lens. It never means apply is safe, drift is absent, or rollback will work.
