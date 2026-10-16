#!/usr/bin/env bash
# Build a source release tarball (X-4).
#
# `st` ships as a checkout, not a single binary: the guard resolves the role
# registry, the schemas, and the team root it protects relative to the tool,
# so bin/st, src/, skills/, and schema/ travel together. A zipapp cannot
# carry skills/ beside the tool, so the release is a source tarball of the
# tracked tree at a tag.
#
# Usage: scripts/release.sh [--tag]
#   --tag   also create an annotated git tag vX.Y.Z (requires a clean tree)
#
# Verified by tests/test_release.py: the tarball unpacks to a tree whose own
# bin/st passes black-box ledger/schema/role smoke tests and a guard corpus case.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

version="$(sed -n 's/^VERSION = "\(.*\)"/\1/p' src/surgical_team/model.py)"
[ -n "$version" ] || { echo "release: cannot read VERSION from model.py" >&2; exit 1; }
prefix="surgical-team-$version"
dist="${ST_DIST_DIR:-dist}"  # the release test builds into its own temp dir
out="$dist/$prefix.tar.gz"
mkdir -p "$dist"

tag=false
[ "${1:-}" = "--tag" ] && tag=true

if $tag; then
  if [ -n "$(git status --porcelain)" ]; then
    echo "release: working tree is dirty; commit before tagging" >&2
    exit 1
  fi
  git tag -a "v$version" -m "surgical-team $version"
  echo "tagged v$version"
fi

# Build from the tag if it exists, else from the current index (so a release
# reflects what is staged, not only the last commit).
if git rev-parse -q --verify "refs/tags/v$version" >/dev/null 2>&1; then
  ref="v$version"
else
  ref="$(git write-tree)"
fi
git archive --format=tar.gz --prefix="$prefix/" -o "$out" "$ref"
echo "built $out from ${ref:0:12} ($(wc -c < "$out") bytes)"
