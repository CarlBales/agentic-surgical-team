# ADR Lifecycle

Architecture decision records preserve why a decision was made and what later
changed it. The archivist maintains the record's structural integrity. The
surgeon decides whether a proposal is accepted, whether a decision is obsolete,
and which later decision supersedes it.

Local ADR conventions always win. Nygard and MADR supply established formats;
they do not authorize migrating a vault or adding fields it did not adopt.

## Nygard's original format

Michael Nygard's 2011 article proposes short, numbered records with these
parts:

- **Title** — a short noun phrase.
- **Context** — the forces at play, stated without advocating a result.
- **Decision** — the response to those forces, in active voice.
- **Status** — proposed or accepted; later deprecated or superseded with a
  reference to the replacement.
- **Consequences** — resulting positive, negative, and neutral effects.

Numbers increase monotonically and are not reused. Reversed decisions remain in
the repository and are marked; history is not rewritten to make the old choice
look as though it never existed.

This is lineage, not a universal schema. A vault may place status in YAML,
spell an identifier differently, omit numbering, or use other lifecycle values.
Apply only its declared format.

Source: Michael Nygard, "Documenting Architecture Decisions," 2011-11-15,
<https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions>.

## MADR 4.0.0

Markdown Architectural Decision Records (MADR) 4.0.0 is a richer released
template. It uses YAML frontmatter for metadata and structures the body around
context and problem, decision drivers, considered options, decision outcome,
consequences, confirmation, and supporting detail. Use the exact released or
locally vendored template the vault names; do not review against the development
branch from memory.

MADR is an alternative to the minimal Nygard form, not a mandatory upgrade.
Mixing headings or metadata from several MADR releases can create a document
that satisfies none of the vault's tooling.

Sources:

- MADR documentation, release news for 4.0.0 — <https://adr.github.io/madr/>
- MADR 4.0.0 templates —
  <https://github.com/adr/madr/tree/4.0.0/template>

## Establish the local lifecycle

Before checking an ADR, answer from repository evidence:

1. Which directories contain ADRs, and are nested scopes independent?
2. How is identity encoded: filename number, frontmatter ID, title, or stable
   link target?
3. Which template and version apply?
4. Which status property or section is authoritative?
5. What exact values are allowed, including spelling and case?
6. Which transitions require a recorded decision or named approver?
7. How are relations represented: `Superseded by`, `Supersedes`, Markdown
   links, wikilinks, IDs, or frontmatter lists?
8. Is one successor required, or can partial supersession branch?
9. Which index or Base exposes current and historical decisions?
10. Is a publication registry downstream of ADR state?

If answers conflict, classify the conflict **JUDGMENT** and stop short of a
lifecycle edit.

## Status is a claim

Typical vocabularies include proposed, accepted, rejected, deprecated, and
superseded. Their exact meanings and capitalization come from the vault.
Do not invent a transition graph from these English words.

Structural checks:

- The status field or section exists where required.
- Its value belongs to the declared vocabulary.
- Its representation has the declared type.
- A superseded state has the relation the local schema requires.
- A non-superseded state does not carry a contradictory supersession relation,
  unless local policy explicitly permits advance linking.
- Indexes and views do not disagree with the authoritative field.

Semantic actions that always require evidence from the surgeon or an active
recorded decision:

- proposed to accepted;
- proposed to rejected;
- accepted to deprecated;
- accepted or deprecated to superseded;
- restoring an older decision;
- choosing a replacement when several candidates exist.

A merged pull request, a newer date, implementation in code, or a later ADR
number may support a question. None alone proves a status transition.

## Supersession edges

Model a relation as a directed edge from the old ADR to its replacement:

```text
ADR-0010 --superseded-by--> ADR-0024
ADR-0024 --supersedes-----> ADR-0010
```

These two statements are reciprocal views of one fact. Under a vault that
requires both, verify:

1. Source and target identities exist.
2. Neither endpoint links to itself.
3. The forward and reverse edge name the same pair.
4. No exact edge is duplicated.
5. Link path and case resolve at the examined commit.
6. Cardinality obeys the local schema.
7. Status and edge agree under the local lifecycle.
8. The directed graph contains no cycle.
9. Every index or Base derives current state consistently.

A missing reciprocal edge can be **MECHANICAL** when one valid edge exists, the
schema requires both, the target is unique, and adding the inverse does not
assert any new relationship. If any premise is absent, it is **JUDGMENT** or
**UNVERIFIED**.

Example:

```yaml
# ADR-0010; existing, declared authoritative relation
status: superseded
superseded_by:
  - "[[ADR-0024]]"

# ADR-0024; inverse missing under a schema that requires it
supersedes:
  - "[[ADR-0010]]"  # MECHANICAL addition
```

Do not copy these property names into another vault. They illustrate the
relation only.

## Chains, branches, and cycles

A replacement chain can be valid:

```text
ADR-0003 -> ADR-0011 -> ADR-0042
```

Call the endpoint current only when local policy defines it that way and no
contradiction intervenes. Preserve all historical records and explicit edges.
A cycle is structurally incoherent for replacement semantics, but removing an
edge chooses which claim is false: report the exact cycle as **JUDGMENT** unless
history proves a path typo.

A branch can represent valid partial supersession, a scope split, or a defect:

```text
ADR-0003 -> ADR-0011
ADR-0003 -> ADR-0012
```

Check list cardinality and context; do not collapse it. A later ADR may also
supersede several old ADRs, so multiple incoming edges are not errors alone.

## Detection with read-only viewers

```bash
rg -n -i --glob '*.md' '^status:|^##?[[:space:]]+status|superseded by|supersedes'
rg -n --glob '*.md' 'ADR[-_ ]?[0-9]+'
git log --oneline -- path/to/adr-directory
git show <head>:path/to/adr.md
```

For pinned review targets, use `git show <head>:<path>` and
`git diff <base>...<head> -- <adr-path>`, not the working copy. Text search can
match prose, examples, and code; it finds candidates, not parsed edges. Prefer
the vault validator at L1. A new checker belongs to the toolsmith.

## Safe mechanical repairs

A repair is **MECHANICAL** only when the declared format gives one result:

- convert a uniquely identified relation scalar to its required one-item list;
- add a required inverse whose opposite endpoint is already explicit;
- update a relation after one exact git rename, preserving stable identity;
- remove an exact duplicate edge from one list;
- correct property spelling when schema, template, and value agree;
- add an index entry only when destination, text, and ordering are prescribed.

Verify both endpoints, graph, index, `.base` consumers, and diff afterward. A
reciprocal repair touches two records; both paths must be in the order.

## Judgment calls

Leave these for the surgeon:

- whether one ADR replaces, narrows, or merely relates to another;
- which conflicting ADR remains current, and every status transition;
- whether a branch is partial supersession;
- whether duplicate ADRs should merge or retain both identities;
- whether to migrate format or template version;
- whether a changed decision requires a new ADR;
- whether a stale proposal should be rejected, withdrawn, or left open.

Ask with evidence: "Should ADR-0018 be marked superseded by ADR-0031? Both
claim the same scope, but neither records a relation."

## Index and navigation consistency

Determine whether an index is hand-maintained, generated, or a `.base` view.
A prescribed missing row can be **MECHANICAL**. Never hand-edit generated
output; hand broken regeneration to the toolsmith. Verify Base filters and
property names against the installed Obsidian version. Separate current from
historical records only under declared status semantics.

A publication registry is downstream. An ADR repair never authorizes a tracker
transition; stage only the local registry diff supported by supplied evidence.

## Characteristic AI mistakes

- **Newer number declared winner — JUDGMENT.** Require an explicit decision.
- **Replaced ADR deleted — JUDGMENT.** Retain history and repair relations.
- **Status advanced because code exists — JUDGMENT.** Ask for the event.
- **Only one endpoint checked — MECHANICAL error.** Verify both and cardinality.
- **Cycle broken arbitrarily — JUDGMENT.** Report the complete cycle.
- **Branch called corruption — UNVERIFIED.** Check partial-replacement policy.
- **External template imposed — JUDGMENT.** Apply the local template.
- **Development MADR called 4.0.0 — UNVERIFIED.** Use the release tag.
- **Tracker changed after repair — L3 violation.** Stage the registry diff.

## Report evidence

For each lifecycle item, record:

```text
label       MECHANICAL | JUDGMENT | UNVERIFIED
source      ADR identity and path:line
counterpart target identity and path:line, or missing
rule        local schema/template path:line
action      exact repair, or one surgeon question
evidence    validator output or labeled prediction
```

List every cycle, judgment branch, and missing endpoint; counts alone hide
broken pairs.
