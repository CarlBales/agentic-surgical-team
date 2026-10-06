#!/usr/bin/env bash
# Validate every skill in skills/ against the Agent Skills specification.
#
# Runs the reference validator (skills-ref) when available, and always runs
# a built-in structural check: frontmatter presence, required fields, name
# rules, name/directory agreement, description length, and relative link
# resolution.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
skills_dir="$root/skills"

[ -d "$skills_dir" ] || {
  echo "error: no skills directory at $skills_dir" >&2
  exit 1
}

fail=0
checked=0

note() { printf '  %s\n' "$1"; }
bad()  { printf '  FAIL: %s\n' "$1"; fail=1; }

# --- reference validator, if present -----------------------------------------
if command -v skills-ref >/dev/null 2>&1; then
  echo "== skills-ref =="
  for skill in "$skills_dir"/*/; do
    name="$(basename "$skill")"
    if skills-ref validate "$skill"; then
      note "$name ok"
    else
      bad "$name rejected by skills-ref"
    fi
  done
  echo
else
  echo "note: skills-ref not installed; running structural checks only."
  echo "      install: cargo install skills-ref   (or see agentskills.io)"
  echo
fi

# --- structural checks -------------------------------------------------------
echo "== structural checks =="
for skill in "$skills_dir"/*/; do
  dir="$(basename "$skill")"
  file="$skill/SKILL.md"
  checked=$((checked + 1))
  printf '%s\n' "$dir"

  if [ ! -f "$file" ]; then
    bad "no SKILL.md"
    continue
  fi

  # Frontmatter must open on line 1.
  if [ "$(head -n 1 "$file")" != "---" ]; then
    bad "frontmatter does not start on line 1"
    continue
  fi

  # Closing delimiter line number.
  close="$(awk 'NR>1 && /^---$/ {print NR; exit}' "$file")"
  if [ -z "$close" ]; then
    bad "frontmatter is not closed"
    continue
  fi
  fm="$(sed -n "2,$((close - 1))p" "$file")"

  # name
  name="$(printf '%s\n' "$fm" | sed -n 's/^name:[[:space:]]*//p' | head -n 1)"
  if [ -z "$name" ]; then
    bad "missing required field: name"
  else
    [ "$name" = "$dir" ] || bad "name '$name' does not match directory '$dir'"
    [ "${#name}" -le 64 ] || bad "name longer than 64 characters"
    printf '%s' "$name" | grep -Eq '^[a-z0-9]+(-[a-z0-9]+)*$' \
      || bad "name '$name' must be lowercase alphanumeric with single hyphens, no leading/trailing hyphen"
  fi

  # description
  desc="$(printf '%s\n' "$fm" | sed -n 's/^description:[[:space:]]*//p' | head -n 1)"
  if [ -z "$desc" ]; then
    bad "missing required field: description"
  else
    len="${#desc}"
    [ "$len" -le 1024 ] || bad "description is $len characters (max 1024)"
    [ "$len" -ge 40 ] || note "warn: description is only $len characters; say what it does and when to use it"
  fi

  # body size guidance
  lines="$(wc -l < "$file" | tr -d ' ')"
  [ "$lines" -le 500 ] || note "warn: SKILL.md is $lines lines; spec recommends under 500"

  # relative links resolve, in every markdown file of the skill.
  # Links inside fenced code blocks are illustrative, not navigation, so
  # they are skipped — assets/ templates contain paths for a future
  # directory that cannot resolve from where the template lives.
  while IFS= read -r md; do
    while IFS= read -r link; do
      [ -n "$link" ] || continue
      case "$link" in
        http*|mailto:*|\#*) continue ;;
        *'<'*) continue ;;   # placeholder such as references/<core-model>.md
      esac
      target="${link%%#*}"
      [ -n "$target" ] || continue
      if [ ! -e "$(dirname "$md")/$target" ]; then
        bad "broken relative link in ${md#"$skill"}: $target"
      fi
    done < <(awk '
      /^[[:space:]]*(```|~~~)/ { fenced = !fenced; next }
      !fenced { print }
    ' "$md" | grep -oE '\]\([^)]+\)' | sed 's/^](//; s/)$//')
  done < <(find "$skill" -name '*.md')

  note "checked ($lines lines)"
done

echo
if [ "$fail" -eq 0 ]; then
  echo "OK: $checked skills passed."
else
  echo "FAILED: see messages above."
fi
exit "$fail"
