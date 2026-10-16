# Vault Conventions

A vault is governed by its own declared conventions. Obsidian, YAML, and
CommonMark define syntax; they do not decide the vault's schema. Read this
reference after the [archivist skill](../SKILL.md) baseline is established.

## Authority order

Use the repository's stated precedence. If it does not state one, gather these
sources without silently ranking contradictory rules:

1. Machine-readable schema and the validator configuration that enforces it.
2. Scoped instructions such as `AGENTS.md`, `VAULT.md`, or a directory README.
3. Canonical templates under `_templates/` or a path named by the vault.
4. Metadata documentation, dictionaries, and examples under `_meta/`.
5. Repeated corpus practice, used only as evidence of a possible convention.

An explicit rule and its validator may still disagree. That is **JUDGMENT**,
not permission to choose the machine because it is easier to run. Record both
paths and the smallest question that resolves precedence.

## YAML frontmatter

Obsidian-style properties occupy a YAML mapping between `---` delimiters at the
start of a Markdown file. Local conventions may prohibit frontmatter, use a
subset of YAML, or require another metadata system; those rules win.

Check, in order:

- The opening delimiter is where the vault requires it. A byte-order mark or
  prose before `---` can prevent recognition by some consumers.
- A closing delimiter exists before the Markdown body.
- The content parses under the parser and YAML version the vault actually uses.
- Mapping keys are unique. Duplicate keys are ambiguous even when a parser
  keeps the last value.
- Property spelling and case match the schema exactly.
- Values have the declared shape: scalar, sequence, mapping, date, number, or
  boolean. A one-element list is still a list.
- Required values are present and non-null according to the local definition of
  "required." Presence with an empty value may not satisfy it.
- Enum values match exactly; do not normalize case unless the schema says to.

Example of a determinate shape repair:

```yaml
# Declared schema: aliases is a sequence of strings.
# Before
aliases: Service map

# After — MECHANICAL when this is the sole value
aliases:
  - Service map
```

Changing `status: draft` to `status: published` is never a shape repair. It is
**JUDGMENT**, because it asserts a lifecycle event.

YAML 1.2.2 does not make every familiar word a boolean, but the vault's parser
may implement older or extended resolution. Quote strings when the local
template does and the value could be retyped by its parser. Do not mass-quote a
corpus merely for visual consistency.

Multiline scalars, anchors, aliases in the YAML sense, explicit tags, and nested
mappings are valid YAML features. They are not necessarily supported property
values in the consuming application. Validate against the consumer, not just a
generic YAML parser.

## Property types and identifiers

Treat identifier-like values as strings unless the schema says otherwise.
Leading zeroes in an ADR number, an issue key, or a catalog code can be lost by
numeric coercion. A date-like identifier can likewise be retyped as a date by a
parser.

For each property, record:

| Question | Evidence |
|---|---|
| Is it required? | explicit schema or all applicable canonical templates plus prose saying it is required |
| What is its type? | schema declaration, validator rule, or unambiguous template value |
| Is it single or repeated? | declared scalar/sequence shape; corpus frequency alone is insufficient |
| What values are allowed? | explicit enum or lifecycle document |
| Is it computed? | generator, Base formula, or documentation naming its owner |
| Is it scoped? | nearest convention file or template family |

A generated or computed property should not be hand-edited unless the order
names the source of truth. Report drift between source and output, then hand it
to the toolsmith if regeneration machinery is broken.

## Inferring a schema from templates

Inference is sometimes necessary, but it must remain visible as inference.
Build a table per template family rather than flattening unlike notes together.

1. Identify canonical templates from documentation, not merely filenames that
   contain `template`.
2. Map each template to the directories or note kinds that use it.
3. List each property, literal/default value, and YAML node kind.
4. Mark a property **explicit** only when prose or schema declares it.
5. Mark a property **inferred** when templates agree but no declaration exists.
6. Treat placeholders such as `{status}` or empty values as unknown type unless
   surrounding documentation resolves them.
7. Compare actual notes to the applicable family, not to a global union.
8. Surface conflicts; do not update templates or schema to match the majority.

**JUDGMENT:** Ninety percent of notes use `owner`, while the canonical template
uses `owners`. Frequency suggests drift but cannot establish which spelling is
right. Ask which property is authoritative.

**MECHANICAL:** The schema and every applicable template require `tags` as a
list, and one note has a single scalar tag with the same text. Convert only the
shape.

**UNVERIFIED:** A template invokes a plugin macro whose expansion supplies
frontmatter, but that plugin and an exported result are unavailable. Name the
plugin output needed; do not reverse-engineer it from guesses.

## Wikilinks

Common Obsidian forms include:

```markdown
[[Note]]
[[folder/Note]]
[[Note|display text]]
[[Note#Heading]]
[[Note#^block-id]]
```

The target is the part before `|`; a heading or block fragment follows `#`.
Resolve it under the vault's link settings and path conventions. Do not assume
the current operating system's case behavior is portable. A link that works on
a case-insensitive filesystem can break after checkout on a case-sensitive one.

A target check has layers:

1. Does exactly one note path resolve?
2. If a heading fragment is present, does that heading exist under the
   consumer's normalization rules?
3. If a block reference is present, is the block identifier present and
   unique where required?
4. Is the display text merely presentation, or is a local convention keeping
   it synchronized with title or alias?

Nearest-name matching is evidence, never a repair rule. A rename visible in git
history, combined with one unique destination and unchanged note identity, can
make a replacement **MECHANICAL**. Two plausible destinations make it
**JUDGMENT**.

Markdown links use a different grammar:

```markdown
[display text](folder/note.md)
[section](folder/note.md#heading)
```

Account for relative paths, angle-bracket destinations, escaped characters,
percent encoding, fragments, and reference-style definitions. Regular
expressions are useful for discovery but not a complete Markdown parser.
CommonMark 0.31.2 defines standard Markdown links; Obsidian extensions and local
plugins can add more.

## Embeds and attachments

An exclamation mark changes a wikilink into an embed:

```markdown
![[Note]]
![[Note#Heading]]
![[diagram.png]]
![[manual.pdf#page=3]]
```

The same target-existence checks apply, plus attachment location and supported
fragment behavior. Do not rewrite a missing attachment link to a similarly
named file without identity evidence. File hashes can show exact content
identity but cannot prove which filename the author intended.

Distinguish deliberately external URLs from vault attachments. Network access
is not implied by a URL in a note, and checking remote link health requires an
order that grants an appropriate source or tool.

## Aliases

Obsidian recognizes aliases through a property convention. The vault decides
whether the property is required, whether aliases are a list, and whether case
or punctuation differences are meaningful.

Check for:

- duplicate aliases within one note;
- one alias claimed by multiple notes;
- an alias equal to another note's canonical title;
- aliases that differ only by case or Unicode normalization;
- links whose display text is mistaken for a target rename.

Removing an exact duplicate list entry is usually **MECHANICAL**. Choosing which
of two notes owns a shared alias is **JUDGMENT**. An alias is not proof that a
bare `[[Alias]]` has a unique durable target; inspect what the application
stored and the vault's rules.

## Tags

In YAML properties, tags are commonly represented as a string or list according
to the application's accepted shape. Inline tags use `#tag` syntax in Markdown.
Local policy decides canonical case, hierarchy, separators, and whether inline
and frontmatter tags may coexist.

Do not add `#` to YAML tag values unless the vault explicitly stores it. Do not
flatten a hierarchical tag such as `area/storage` into two tags. Do not merge
case variants until the surgeon confirms they are synonymous under the vault's
policy.

A taxonomy rename affects saved searches, Bases, indexes, and external publish
registries. Inventory all consumers before proposing it; execution requires an
explicitly scoped order.

## Obsidian Bases awareness

A `.base` file describes database-like views over notes and their properties.
It can depend on property names, paths, tags, formulas, filters, sorting, and
view configuration. The format evolves with Obsidian, so record the installed
application version and use its matching official documentation.

Before changing a property or moving a note, search `.base` files for the old
name and path. A Base continuing to parse does not prove its view still selects
the intended notes. Property renames, type changes, and enum changes are
**JUDGMENT** unless an approved migration defines both sides.

Do not hand-edit generated Base output. `.base` definitions are authored
configuration; rendered tables or exports may be generated artifacts. The
vault's conventions must identify which is which.

## Characteristic AI mistakes

- **Schema invented from prevalence — JUDGMENT.** Report the dominant pattern and conflicting declared source; ask which governs.
- **Links repaired by edit distance — JUDGMENT.** Require unique identity evidence such as a documented rename or stable ID.
- **All YAML normalized — JUDGMENT.** Change only schema-required shape; preserve comments, ordering, quoting, and body text.
- **Every orphan treated as garbage — JUDGMENT.** Exclude entry points, templates, indexes, archives, and intentional standalone notes.
- **Display text confused with target — MECHANICAL error.** Parse the target before `|`; leave presentation unchanged unless ordered.
- **`.base` consumers ignored — MECHANICAL error.** Inventory property references before a determinate rename.
- **Filesystem case behavior assumed — UNVERIFIED.** Compare exact tracked path case and report portability risk.
- **Visual inspection called parser acceptance — UNVERIFIED.** Run the vault validator at L1 or name the missing check.

## Sources

- YAML 1.2.2 — <https://yaml.org/spec/1.2.2/>
- CommonMark 0.31.2 — <https://spec.commonmark.org/0.31.2/>
- Obsidian Help, unversioned: <https://help.obsidian.md/properties>, <https://help.obsidian.md/links>, <https://help.obsidian.md/embeds>, and <https://help.obsidian.md/bases>. Record app version and access date.
