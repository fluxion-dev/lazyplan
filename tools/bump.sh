#!/usr/bin/env bash
# Bump the lazyplan semantic version: major | minor | patch.
# Single source of truth is `version = "x.y.z"` in pyproject.toml; the
# README header (`# lazyplan (`lp`) — v0.7.0`) mirrors it and is updated here.
# Commits the change and tags `vX.Y.Z` (annotated). Push with --push.
#
# Usage: ./tools/bump.sh patch [--push] | [--dry-run]
#        ./tools/bump.sh minor --push
set -euo pipefail
cd "$(dirname "$0")/.."

PART="${1:-}"
PUSH=0
DRY=0
for arg in "$@"; do
  case "$arg" in
    --push) PUSH=1 ;;
    --dry-run) DRY=1 ;;
  esac
done

if [[ "$PART" != "major" && "$PART" != "minor" && "$PART" != "patch" ]]; then
  echo "usage: ./tools/bump.sh (major|minor|patch) [--push] [--dry-run]" >&2
  exit 2
fi
if [[ $DRY -eq 0 ]] && [[ -n "$(git status --porcelain)" ]]; then
  echo "error: working tree is dirty — commit or stash first (or use --dry-run)" >&2
  exit 1
fi

CURRENT="$(sed -n 's/^version = "\(.*\)"$/\1/p' pyproject.toml)"
if ! [[ "$CURRENT" =~ ^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]]; then
  echo "error: pyproject version '$CURRENT' is not plain X.Y.Z semver" >&2
  exit 1
fi

NEXT="$(python3 - "$PART" "$CURRENT" <<'EOF'
import sys
part, current = sys.argv[1], sys.argv[2]
major, minor, patch = (int(x) for x in current.split("."))
if part == "major":
    major, minor, patch = major + 1, 0, 0
elif part == "minor":
    minor, patch = minor + 1, 0
else:
    patch += 1
print(f"{major}.{minor}.{patch}")
EOF
)"

if git rev-parse "v$NEXT" >/dev/null 2>&1; then
  echo "error: tag v$NEXT already exists" >&2
  exit 1
fi

echo "$CURRENT -> $NEXT"
if [[ $DRY -eq 1 ]]; then
  echo "(dry run: no files changed)"
  exit 0
fi

sed -i.bak "s/^version = \".*\"$/version = \"$NEXT\"/" pyproject.toml && rm pyproject.toml.bak
sed -i.bak "1s/ — v[0-9][0-9.]*$/ — v$NEXT/" README.md && rm README.md.bak
if ! grep -q "^version = \"$NEXT\"$" pyproject.toml; then
  echo "error: pyproject update failed" >&2
  exit 1
fi
if ! head -1 README.md | grep -q " — v$NEXT$"; then
  echo "error: README header update failed" >&2
  exit 1
fi

git add pyproject.toml README.md
git commit -m "release v$NEXT"
git tag -a "v$NEXT" -m "lazyplan v$NEXT"
echo "committed + tagged v$NEXT"
if [[ $PUSH -eq 1 ]]; then
  git push origin HEAD
  git push origin "v$NEXT"
fi
