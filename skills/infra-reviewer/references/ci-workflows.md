# Reviewing GitHub Actions Workflows
Review workflows as privileged programs. Event payloads and repository content are inputs; `GITHUB_TOKEN`,
secrets, OIDC, runners, caches, and artifacts are capabilities. The exact behavior is versioned in the [GitHub
Actions documentation](https://docs.github.com/actions).

This reference covers GitHub-hosted semantics. For another forge, hand off or cite that platform's
documentation rather than transferring GitHub assumptions.
## Establish the trust boundary
For every changed workflow, record:

1. event and activity types;
2. which repository/ref supplies the workflow definition;
3. which ref is checked out and executed;
4. actor and whether contributions can come from forks;
5. token permissions at workflow and job scope;
6. secrets, environments, OIDC, artifacts, and caches available;
7. runner kind, labels, persistence, and network reach;
8. called and calling workflows;
9. third-party actions and their exact refs.

Do not review only the changed job. A workflow-level permission, reusable workflow, composite action,
environment, or preceding artifact can change the job's authority.
## Token permissions
Declare the smallest `permissions` needed. An omitted declaration inherits repository/organization defaults,
which the repository may not reveal. Put the effective default under `Unverified`; do not call it read-only
from memory.

- A workflow-level map sets the baseline for all jobs.
- A job-level map can narrow or change permissions for that job.
- `contents: read` is usually enough to checkout source.
- Write permissions need a task-specific reason and a trusted event boundary.
- `id-token: write` permits requesting an OIDC token; it does not itself grant
  cloud permissions. The cloud trust policy completes the grant.

**WRONG:** an untrusted pull-request path receives write-capable repository
permissions or a cloud role without a reviewed need and boundary. Minimal fix:
run untrusted validation with read-only/no secrets, and move privileged work to
a separately trusted, approved path.

**UNIDIOMATIC:** `write-all` for a job that only reads and builds. The concrete
cost is that one script/action compromise can alter more repository resources.
Minimal fix: name only required scopes.

Do not invent a permission scope. Verify names in GitHub's workflow syntax docs.
## Event semantics
### `pull_request`
Use for validation of proposed code. Fork-originated runs have platform secret and token restrictions, but
exact behavior depends on repository settings, event subtype, and rerun actor. Record those as unknown unless
supplied.

Code from the proposed change is untrusted. Running it—build scripts, package install hooks, test setup,
Makefiles, local actions—is code execution on the runner. Keep credentials and durable self-hosted runners out
of that boundary.
### `pull_request_target`
This event runs the workflow from the base branch context and is useful for trusted metadata operations. It is
dangerous when the workflow then checks out or executes pull-request head code while retaining base-context
secrets or write authority.

**WRONG:** `pull_request_target` plus checkout of the contributor-controlled
head followed by build/test/script execution in a privileged job. Minimal fix:
use `pull_request` for untrusted execution, or keep the target workflow strictly
to trusted metadata without executing head content.

Do not claim the event itself is always wrong. Labeling, commenting, or triage can be valid when inputs are
safely handled and permissions are narrow; posting those effects remains the surgeon's L3 concern in this
team.
### Other privileged triggers
For `workflow_run`, `workflow_call`, manual dispatch, schedules, releases, and pushes, ask what artifact/ref
crosses from a less-trusted producer. A trusted trigger does not cleanse an untrusted artifact.

Reusable workflows must constrain inputs and secrets. `secrets: inherit` broadens availability; flag it when
the callee needs only named secrets.
## Script and expression injection
GitHub expressions can contain attacker-controlled titles, branch names, labels, commit messages, issue
bodies, and event fields. Interpolating such a value directly into a shell `run:` block lets shell syntax
change the command.

**WRONG:**

```yaml
- run: echo "${{ github.event.pull_request.title }}"
```

The quotes are parsed after expression substitution and are not a security boundary. Minimal fix: pass the
value through an environment variable, then quote the variable according to the selected shell:

```yaml
- env:
    PR_TITLE: ${{ github.event.pull_request.title }}
  run: printf '%s\n' "$PR_TITLE"
```

This fixes shell parsing for this use; it does not make the value safe for SQL, JSON, regular expressions,
paths, or a later interpreter. Review each boundary.

Pin or declare the shell when behavior depends on shell semantics. Avoid writing untrusted data to command
files without using GitHub's documented multiline/delimiter mechanism and collision-safe handling.
## Action and dependency pinning
A tag or branch is mutable. For third-party actions, a full commit SHA is the strongest immutable Git ref
GitHub workflows accept. Keep a comment with the human-readable release so update tools and reviewers can
identify provenance.

```yaml
- uses: owner/action@0123456789abcdef0123456789abcdef01234567 # vX.Y.Z
```

The SHA above is illustrative, not a real recommendation. Never invent a SHA; copy it from an authenticated
upstream release and verify ownership.

Review:

- owner/repository spelling for typosquatting or transfer;
- full SHA versus mutable tag/branch;
- action source and release provenance;
- transitive tools downloaded by the action;
- whether a local action comes from untrusted checked-out content;
- Docker image tags/digests and package install lock files;
- changed SHA with unchanged comment, or vice versa.

**WRONG:** a privileged workflow changes a third-party action to an unreviewed
moving branch. Minimal fix: pin the reviewed commit and record its release.

A GitHub-owned action is not automatically safe to leave mutable. Apply the repository's supplied pinning
policy consistently; classify deviations by that policy and consequence.
## Secrets and logs
Map every secret from source to process, file, command, log, artifact, cache, service container, and child
process. Masking is a logging mitigation, not an authorization boundary; transformed or structured values may
not be masked.

Check for:

- secrets passed to an entire job or broad environment instead of one step;
- command tracing, debug output, exception dumps, or HTTP verbose logs;
- secret values placed in command arguments visible to process inspection;
- credentials copied into build contexts or artifacts;
- artifacts uploaded on failure that include home directories, env dumps,
  Terraform plans/state, package configs, or cloud credentials;
- untrusted code running before or after credentials are configured;
- long-lived static cloud keys where narrow OIDC federation is available;
- environment secrets used without the expected approval/protection evidence.

**WRONG:** uploading a Terraform plan JSON to a broadly accessible artifact
without classifying it as secret-bearing. Minimal fix: avoid upload, redact by
constructing a safe summary, or constrain retention/access under an explicit
policy.

Never print a suspect value to test masking. Ask the surgeon to rotate a leaked credential; do not rotate it
yourself.
## OIDC federation
OIDC removes stored cloud credentials only when cloud trust is narrow. Review both workflow and cloud-side
trust artifact; one without the other is insufficient evidence.

Workflow checks:

- `id-token: write` appears only on the job needing federation;
- repository contents and third-party code are trusted before token issuance;
- action inputs identify the intended audience/role according to exact docs;
- session duration and name are bounded when configuration exposes them;
- no static credential silently takes precedence.

Trust-policy checks:

- issuer and audience are exact for the integration;
- subject constrains repository and the intended branch, tag, pull-request, or
  protected environment form;
- organization/repository wildcards do not admit unintended workloads;
- the assumed role itself has least privilege and a suitable boundary;
- forks and reusable workflows cannot manufacture an accepted subject.

**WRONG:** production role trust accepts every branch and environment of a
repository whose pull requests execute contributor code. Minimal fix: bind the
subject to a protected deployment identity and separate validation authority.

OIDC claims and subject forms evolve. Cite GitHub's current OIDC reference and the cloud provider's exact
trust documentation; never invent a claim key.
## Caches and artifacts
Caches and artifacts cross jobs and sometimes trust levels. Treat their keys, contents, retention, producer,
and consumer as part of the execution chain.

- An untrusted job must not populate executable content later consumed by a
  privileged job without validation.
- Cache keys based only on a broad branch or user-controlled value invite
  poisoning or accidental sharing.
- Restore keys intentionally broaden matches; review every prefix.
- Never cache credentials, state, plans, signing material, or configuration
  containing tokens.
- Artifact names do not authenticate contents. Pin the producer run/ref and
  validate expected files before use.
- Extraction can overwrite paths; use platform-maintained actions and avoid
  consuming arbitrary archives with privilege.

**WRONG:** a privileged deploy job executes an artifact produced by an
untrusted pull-request run without provenance/content validation. Minimal fix:
rebuild from the reviewed commit in the trusted job or cryptographically verify
a narrowly defined artifact under an approved design.
## Self-hosted runners
A self-hosted runner can preserve files, processes, credentials, network access, and modifications between
jobs. Repository labels are scheduling selectors, not isolation proof.

Untrusted fork code on a durable self-hosted runner is presumptive **WRONG** unless the order supplies
evidence of ephemeral, isolated runners and network/ credential boundaries. Put runner lifecycle and isolation
under `Unverified` when configuration lives outside the repository.

Do not recommend a self-hosted runner merely to access a private network. That is an architecture and
threat-model decision for the surgeon/security reviewer.
## Workflow concurrency and environments
Concurrency controls can prevent overlapping deployment jobs but can also cancel a run after partial external
effects. Review group keys and cancellation semantics against the task. Do not assert rollback from
cancellation.

Environments can gate secrets and deployment, but repository YAML alone may not show protection rules. Record
the named environment; put reviewers, wait rules, branch restrictions, and configured secrets under
`Unverified` unless supplied through an allowed read-only source.
## Characteristic AI-generated mistakes
- Adding `permissions: write-all` because one step failed. **WRONG.** Identify
  the exact scope and trusted job first.
- Pinning an action to a plausible but fabricated SHA. **WRONG.** Verify the
  upstream commit; otherwise leave an explicit unresolved requirement.
- Using `pull_request_target` to “get secrets for tests.” **WRONG** when head
  code runs. Separate untrusted validation from privileged metadata/deploy.
- Quoting `${{ ... }}` directly in shell and calling it sanitized. **WRONG.**
  Cross the expression/shell boundary through a quoted environment variable.
- Assuming forks never receive authority, ignoring settings and reruns.
  **WRONG.** Cite supplied settings or mark effective behavior unverified.
- Switching to OIDC but leaving broad cloud `sub` trust. **WRONG.** Federation
  changes credential delivery, not authorization scope.
- Uploading “all logs” or workspace files on failure. **WRONG** when secret or
  executable material is included; allowlist diagnostic files.
- Treating action pinning as the whole supply-chain review. **UNIDIOMATIC.**
  Downloaded tools, local actions, containers, and install scripts remain.
- Enabling caches everywhere. **TASTE** until a concrete poisoning, isolation,
  staleness, or cost issue is shown.
## Review output
Each workflow finding names the workflow and head line, trigger, attacker- controlled input, available
capability, execution path, smallest boundary fix, and exact GitHub/cloud documentation version. Put effective
repository settings, environment protection, runner isolation, and live trust policy under `Unverified` unless
the order supplies them.
