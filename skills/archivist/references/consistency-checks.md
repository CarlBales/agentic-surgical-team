# Consistency Checks

Use the vault's own validator first. These checks support inventory, triage, and
explanation; they are not a universal validator. Commands below are read-only
viewers when run as shown. At L0, do not invoke a repository script, plugin,
scanner, or validator merely because it claims a check mode: it may write a
cache. At L1, run such tools only inside the order's workspace.

Replace example paths and property names with those declared by the vault.
Never paste a placeholder as if it were a project command.

## Read-only inventory

Start from tracked or visible files, depending on the order:

```bash
git ls-files -- '*.md' '*.yaml' '*.yml' '*.base'
rg --files -g '*.md' -g '*.yaml' -g '*.yml' -g '*.base'
rg --files -g 'README.md' -g 'AGENTS.md' -g 'VAULT.md'
rg --files | rg '(^|/)(_templates|_meta|schema|schemas)(/|$)'
```

`git ls-files` answers what the examined commit tracks. `rg --files` answers
what the current tree exposes after ignore rules. A mismatch can be expected in
a worktree; explain which population each count uses.

For a pinned review target, stay on the supplied SHAs:

```bash
git diff --stat <base>...<head> -- <vault-path>
git diff <base>...<head> -- <vault-path>
git log --oneline <base>..<head> -- <vault-path>
git show <head>:<path>
```

Use the literal values printed in the briefing. Three-dot diff shows changes
from the merge base to `head`; two-dot log lists commits reachable from `head`
and not `base`. Do not quietly substitute another range.

## Check 1: convention sources

Detect:

```bash
rg -n -i 'frontmatter|propert(y|ies)|schema|template|wikilink|alias|tag|status|validator' \
  README.md AGENTS.md VAULT.md _meta _templates 2>/dev/null
```

The paths are illustrative; inspect only those that exist and are in scope.
Record exact path and line for every governing rule.

- **MECHANICAL:** One scoped convention clearly governs and a note violates its
  exact spelling or shape.
- **JUDGMENT:** Two applicable sources disagree, or scope precedence is absent.
- **UNVERIFIED:** A convention references an unavailable plugin, remote schema,
  generated file, or external handbook.

Safe fix: none to the convention itself unless the order explicitly asks for
it. Apply a clear convention to in-scope notes; ask about conflicts.

## Check 2: frontmatter boundaries and keys

Discover candidate delimiters and known properties:

```bash
rg -n --glob '*.md' '^---[[:space:]]*$'
rg -n --glob '*.md' '^(title|aliases|tags|status|date):[[:space:]]*'
sed -n '1,80p' path/to/note.md
```

The property alternation is an example, not a built-in schema. Replace it with
keys read from the vault. `rg` can find candidates but cannot parse YAML or
associate a closing delimiter reliably.

- **MECHANICAL:** A declared list property has one scalar value and preserving
  that value in a one-item list is the unique correction.
- **JUDGMENT:** A required property is absent but its value cannot be derived
  exactly; duplicate keys disagree; an opening delimiter has no obvious close.
- **UNVERIFIED:** Parseability is uncertain without the project's parser.

Safe fix: shape, spelling, or delimiter repairs only when both intended value
and body boundary are unambiguous. Never choose between duplicate values.

## Check 3: schema conformance

Inspect schema and templates with viewers appropriate to their format:

```bash
sed -n '1,240p' path/to/schema.yaml
sed -n '1,160p' path/to/template.md
jq '.' path/to/schema-or-export.json
```

`jq` is for JSON only. It does not parse YAML. Use a repository-documented YAML
viewer or validator at L1 rather than inventing a `yq` expression against an
unknown implementation.

Check required keys, exact names, node kinds, enum values, formats, and scoped
template family. Keep explicit rules separate from inferred regularity.

Safe fix: deterministic representation changes that preserve the same value.
Judgment: supplying missing semantic values, selecting an enum, changing a
schema, or reconciling two template families.

## Check 4: links and embeds

Find candidates; regex is discovery, not a Markdown parser:

```bash
rg -n --glob '*.md' '!?\[\[[^]]+\]\]'
rg -n --glob '*.md' '\[[^]]+\]\([^)]+\)'
git ls-files -- '*target-name.md'
rg -n --glob '*.md' '^#{1,6}[[:space:]]+Heading[[:space:]]*$'
rg -n --glob '*.md' '\^block-id([[:space:]]|$)'
```

Separate target, display text, heading, and block fragment; compare exact
tracked path case. **MECHANICAL:** history shows one exact rename and one
successor. **JUDGMENT:** several titles, aliases, or fragments are plausible.
**UNVERIFIED:** plugin grammar or a generated target is unavailable. Preserve
display text and require identity evidence; spelling similarity is insufficient.

## Check 5: aliases and tags

```bash
rg -n --glob '*.md' '^(aliases|tags):[[:space:]]*'
rg -n --glob '*.md' '(^|[[:space:]])#[[:alnum:]_/-]+'
rg -n --glob '*.base' 'aliases|tags'
```

Use local property names and exclude examples with the vault parser. Removing
an exact duplicate list item can be **MECHANICAL**. Alias ownership, taxonomy,
case, hierarchy, or moving tags between body and frontmatter is **JUDGMENT**.

## Check 6: duplicate notes

Distinguish stable-ID, case-folded path, title/alias, byte-content, normalized
body, and subject-matter duplicates:

```bash
shasum path/to/one.md path/to/two.md
rg -n --glob '*.md' '^id:[[:space:]]*'
rg -n --glob '*.md' '^title:[[:space:]]*'
```

A checksum proves content identity, not which identity survives. Deleting,
merging, redirecting, or assigning a new ID is **JUDGMENT** unless an explicit
generated-file policy names the disposable copy.

## Check 7: orphans and navigation

Define graph edges before counting: wikilinks, Markdown links, embeds, aliases,
Bases, generated indexes, and registry links. Exclude declared roots, maps,
templates, archives, daily notes, attachments, and standalone notes. A Base or
search can be intentional discovery.

**MECHANICAL:** convention gives every note kind one exact index, row format,
and sort position. **JUDGMENT:** choose an index, link text, or obsolescence.
**UNVERIFIED:** generated navigation is unavailable. Never add links merely to
make the orphan count zero.

## Check 8: stale status and dates

Use property names from the schema:

```bash
rg -n --glob '*.md' '^(status|review_after|updated):[[:space:]]*'
git log -1 --format='%H %aI' -- path/to/note.md
git blame -L <start>,<end> -- path/to/note.md
```

Dates and commits are evidence, not lifecycle events. A declared date rule can
make "review due" **MECHANICAL** to detect, but never proves review completion
or a semantic transition. Leave status changes as **JUDGMENT**.

## Check 9: Bases consumers

```bash
rg -n --glob '*.base' 'property-name|old/path|status-value'
sed -n '1,240p' path/to/view.base
```

Matches are candidates because formulas and quoting matter. Updating an exact
reference is **MECHANICAL** only inside an approved, fully scoped rename.
Changing formulas, filters, sorting, or membership is **JUDGMENT**. Rendered
behavior remains **UNVERIFIED** without the matching Obsidian version at L1.

## Check 10: ADR relations

```bash
rg -n -i --glob '*.md' '(^|[[:space:]])status:|superseded by|supersedes'
rg -n --glob '*.md' 'ADR[-_ ]?[0-9]+'
```

Apply [adr-lifecycle.md](adr-lifecycle.md). Reciprocal-edge or path repair is
**MECHANICAL** only with one established pair and local rule. Status transitions
and deciding which record wins are **JUDGMENT**.

## Check 11: publication registry

Find a registry only through conventions or the order. Inspect a supplied JSON
export and the staged local diff:

```bash
jq '.' path/to/tracker-export.json
git diff -- path/to/publish-registry
```

`inputs.sources` may grant named read-only list/get/describe operations; it
never grants create, update, comment, transition, or publish. A declared mapping
plus supplied evidence can make one registry edit **MECHANICAL**. Conflicting
state is **JUDGMENT**. Required tracker truth without an export or signed source
is **UNVERIFIED** and, when criterion-blocking, `BLOCKED`.

## Validation and evidence

At L1, run the vault-documented validator and record literal command, version,
exit status, and concise output. At L0, write `PREDICTION — UNVERIFIED`, state
the expected result, and name the L1 check still required. A clean search is
not a validator result.

Inspect repaired paths:

```bash
git status --short -- <vault-path>
git diff --check -- <vault-path>
git diff -- <vault-path>
```

`git diff --check` finds whitespace errors only. It says nothing about YAML,
links, or schema. Report population (tracked or visible), exclusions, commit,
and scope with every count.

## Characteristic AI mistakes

- **Regex called a parser — UNVERIFIED.** Run the local parser at L1.
- **Nearest filename selected — JUDGMENT.** Require unique identity evidence.
- **Plausible metadata supplied — JUDGMENT.** Preserve the gap and ask.
- **Status advanced from dates — JUDGMENT.** Require the lifecycle event.
- **Exact duplicate deleted — JUDGMENT.** Show hashes and inbound links first.
- **Clean diff called clean vault — UNVERIFIED.** Separate git and vault checks.
- **Scanner run at L0 — protocol violation.** Use viewers or request L1.
- **Tracker updated from registry — L3 violation.** Stage only the local diff.
- **Counts lack population — UNVERIFIED.** State tree, scope, and exclusions.
