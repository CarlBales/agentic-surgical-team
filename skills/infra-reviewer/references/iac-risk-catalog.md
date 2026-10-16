# Infrastructure-as-Code Risk Catalog
Use this catalog after establishing engine, provider, module, environment, and policy versions. It is a set of
review prompts, not universal policy. A pattern becomes a finding only when the reviewed configuration and
baseline support the claim.

Provider behavior is versioned. Cite the exact resource and attribute docs from the provider version selected
in `.terraform.lock.hcl`; do not rely on the current website when the lock selects an older release.
## Identity and access
Read an IAM statement as a tuple:

```
principal -> action -> resource -> conditions -> effect
```

Then compose statements, attachments, trust policies, permission boundaries, service control policies when
supplied, resource policies, and role chaining. A narrow-looking statement can complete an escalation path
with another one.
### Wildcards
- `Action: "*"` and `Resource: "*"` together are presumptive **WRONG** unless
  an explicit decision and an effective outer boundary constrain them.
- A wildcard resource is sometimes required for list/describe actions. Cite the
  service authorization reference before demanding an impossible resource ARN.
- Prefix wildcards such as `service:Get*` expand as APIs evolve. State that
  future breadth; do not invent current actions.
- `NotAction` and `NotResource` are easy to misread. Evaluate them with `Effect`
  and policy scope; they do not mean “everything except” in isolation.

Minimal fixes prefer explicit actions, resource ARNs, and conditions grounded in stable identity attributes.
Do not recommend a condition key until verified in the exact service documentation.
### Escalation combinations
Search for the ability to:

- pass a role and create or update compute/function/task execution;
- modify a role trust policy, attach policies, create policy versions, or add a
  principal to a privileged group;
- invoke a privileged function or automation document;
- update code, startup data, build definitions, or deployment definitions that
  run under a stronger role;
- decrypt or read secrets and then use credentials they contain;
- alter resource policies, key policies, or identity-provider configuration.

Do not label a path **WRONG** until every required edge is present or explicitly unverified. Name each edge
and the missing evidence. `iam:PassRole` alone is not a complete escalation path, but broad PassRole plus a
usable execution service is often one.
### Trust policies
The trust policy answers who may obtain the role, not what the role may do. Check AWS principals, services,
federated identities, OIDC claims, account-root principals, external IDs, organization/account restrictions,
audience, subject, and session assumptions as relevant.

**WRONG:** a federated trust accepts any repository/branch subject while the
role can alter production infrastructure. Minimal fix: constrain audience and
subject to the intended identity, and use environment protection where the
platform supports it.

**UNIDIOMATIC:** several unrelated workloads share one role, obscuring
attribution and forcing a union of permissions. Minimal fix: split roles at the
actual trust and permission boundary.
## Network reachability
Review both address families. `0.0.0.0/0` says nothing about IPv6; `::/0` says nothing about IPv4.

For every ingress path, trace:

1. public/private address and DNS;
2. internet gateway, route, load balancer, proxy, CDN, or tunnel;
3. security-group/firewall source and port/protocol;
4. network ACL or equivalent, if supplied;
5. application authentication and TLS only when evidence is in scope;
6. the final resource and any management/control port.

Public `0.0.0.0/0` or `::/0` ingress is a finding unless exposure is explicit, bounded to the intended
listener, and protected by shown controls. SSH, RDP, database, cache, orchestration, and administrative ports
open globally are normally **WRONG**. An HTTPS listener can be intentional; do not call public web ingress
wrong merely because it is public.

Default egress to all destinations is not automatically WRONG. State the threat model and operational cost
before recommending restriction. Egress controls that omit DNS, package mirrors, identity endpoints, or
provider control planes can make recovery impossible.
### Storage and service exposure
Check all layers, not one boolean:

- account-level and resource-level public-access blocks;
- ACLs and ownership mode;
- bucket/container/resource policy principals and conditions;
- website hosting or public endpoint settings;
- cross-account grants, access points, and replication identities;
- encryption, key policy, transport requirements, versioning, retention, and
  deletion protection where supported;
- logs that may include request bodies, authorization data, or signed URLs.

**WRONG:** a public resource policy added while a public-access block is removed,
without an explicit public-data decision. Minimal fix: restore blocks and scope
the principal, or obtain the public-exposure decision with data classification.
## Secrets, variables, outputs, and state
Terraform/OpenTofu sensitivity controls presentation, not storage. State and saved plans can contain secrets
in clear text. A `sensitive = true` variable or output does not encrypt the value.

Review for:

- literal credentials, private keys, tokens, connection strings, or passwords in
  `.tf`, `.tfvars`, workflow YAML, user data, templates, and examples;
- secret values passed through resource arguments and therefore stored in state;
- outputs exposing secret-bearing objects or URLs;
- generated random values whose state backend is not protected;
- command provisioners or workflow logging that echoes variables;
- broad read access to state, plans, artifacts, caches, and logs.

**WRONG:** committing a real secret, even in a “temporary” variable default.
Minimal fix: remove and rotate it, then pass it through an approved secret
channel. Rotation is a surgeon/security operation; do not perform it.

**UNIDIOMATIC:** outputting a whole resource object when callers need one
non-sensitive identifier. Minimal fix: output the smallest stable value and
mark sensitivity according to actual content.
## State, addresses, and drift
Inspect backend configuration without assuming omitted values are unsafe; many backends receive credentials
and options out of band. Record what cannot be seen.

Look for:

- local state where team/automation use requires shared locking and recovery;
- backend changes that imply migration but have no explicit order;
- encryption, access control, locking, version recovery, and audit evidence;
- unstable `count` indexes where insertion shifts durable objects;
- `for_each` keys derived from mutable display names;
- resource/module renames without `moved` declarations;
- provider default changes masquerading as drift;
- manual console settings hidden by `ignore_changes`.

**WRONG:** an address refactor plans deletion and creation of a durable volume
without a move or migration decision. Minimal fix: preserve state identity with
a version-supported moved declaration, or give the surgeon exact reviewed
state-operation steps.
## Lifecycle controls
Lifecycle arguments change graph and update behavior; none is a universal safety switch.
### `prevent_destroy`
Useful for a narrow class of durable resources. It blocks a plan that would destroy while the resource remains
configured, but it does not protect an object after its entire configuration is removed. It can also block
legitimate recovery.

- Missing `prevent_destroy` is not automatically a finding.
- Adding it to every resource is **UNIDIOMATIC**; it turns routine replacement
  into emergency override work.
- A stateful destroy still needs review even when `prevent_destroy` exists.
### `create_before_destroy`
It can reduce downtime, but may require simultaneous names, addresses, quotas, attachments, and capacity. It
does not migrate data or traffic by itself.

**WRONG:** asserting zero downtime solely because this setting is present.
Minimal fix: provide cutover, health, capacity, and rollback evidence.
### `ignore_changes`
Use for a named attribute owned by another controller, with that ownership boundary documented. Broad or
unexplained ignores hide drift and can freeze a security-sensitive setting.

**WRONG:** ignoring policy, network exposure, encryption, image, or secret
version changes to make a noisy plan empty, unless an explicit controller and
reconciliation path owns that field. Minimal fix: remove the ignore or narrow
it to the externally owned path and document ownership.
## Versions and supply chain
Separate compatibility constraints from immutable selections:

- `required_version` constrains the engine; it does not install or select one.
- `required_providers` identifies source and allowed versions.
- `.terraform.lock.hcl` records selected provider versions and package hashes;
  review unexpected source, version, platform hash, and checksum churn.
- Registry module versions are selections; VCS module `ref` values can be tags,
  branches, or commit IDs. A branch and many tags are mutable.
- Local module sources are reviewed with the same change.
- Generated CDK/provider output must be attributable to pinned tooling.

An open range is not necessarily wrong, because the lock file selects a provider for normal installation.
Missing constraints plus an absent lock file makes reproduction dependent on retrieval time and is usually
**UNIDIOMATIC** or **WRONG** when provider changes can alter production behavior.

**WRONG:** changing a module source to a moving default branch for a privileged
or stateful stack. Minimal fix: select an reviewed immutable release or commit
and record the upgrade evidence.
## Naming, tags, and ownership
Match repository conventions before judging style. Names and tags become risk controls when automation,
policy, billing, retention, incident response, or ownership depends on them.

- Missing owner/data-class/environment tags are WRONG only when a supplied
  policy requires them.
- Duplicated tag maps are **UNIDIOMATIC** when they drift; centralize defaults
  without hiding resource-specific tags.
- Renaming a provider-addressed object can force replacement. Never suggest a
  cosmetic rename without plan evidence.
- A random suffix is not automatically good or bad. It trades stable discovery
  for collision avoidance and replacement flexibility.

**TASTE:** two local/tag-map layouts are equally readable, preserve resource
addresses, and produce the same plan. No fix is required; match the repository.
## CloudFormation and CDK lighter pass
For CloudFormation, inspect resource replacement semantics in the exact resource specification, parameters and
`NoEcho` limits, IAM capabilities, conditions, cross-stack exports, `DeletionPolicy`, `UpdateReplacePolicy`,
dynamic references, custom resources, and rollback implications. `NoEcho` does not remove a secret from every
template metadata or downstream service.

For CDK, source code is not the deployment contract: constructs synthesize resources, policies, assets, custom
resources, and logical IDs. Review supplied synthesized templates when blast radius matters. If none is
supplied, put the synthesized resource/policy set under `Unverified`; do not run synthesis at L0.

**WRONG:** a stateful CloudFormation resource lacks the retention/replacement
behavior required by an explicit decision. Minimal fix: set the documented
policies and verify the resulting change set before execution.
## Characteristic AI-generated mistakes
- Invented resource arguments or copied attributes from another provider
  version. **WRONG.** Verify exact version docs.
- Broad IAM wildcards added because generated code cannot enumerate calls.
  **WRONG** when effective privilege exceeds intent. Derive actions from the
  workload and service authorization reference.
- `prevent_destroy` and `create_before_destroy` pasted onto every resource.
  **UNIDIOMATIC.** Choose lifecycle from failure and replacement behavior.
- `ignore_changes = all` used to silence drift. **WRONG** when Terraform is
  still represented as managing security or durability.
- Secret defaults and outputs filled with realistic placeholders that become
  real credentials later. **WRONG.** Use explicit inputs and secret channels.
- “Best-practice” encryption/logging/tagging added without checking region,
  service support, retention cost, or repository policy. Usually
  **UNIDIOMATIC**; split policy decisions from correctness.
- Comments claiming a bucket or role is private/least-privilege while policy
  says otherwise. **WRONG.** Controls, not comments, are evidence.
- Terraform syntax reviewed as if it proves a plan. **WRONG.** Require the
  supplied plan for blast-radius conclusions.
## Citation discipline
Cite provider resources and attributes at their selected version, Terraform or OpenTofu language behavior at
the producing version, AWS IAM behavior from the [IAM User
Guide](https://docs.aws.amazon.com/IAM/latest/UserGuide/), and CIS controls only with the exact benchmark,
profile, cloud, and version supplied by the order. Never invent a benchmark control or claim CIS compliance
from a partial code review.
