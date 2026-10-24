#!/usr/bin/env bash
# Bump the lazyplan semantic version: major | minor | patch.
# Single source of truth is `version = "x.y.z"` in pyproject.toml; the
# README header (`# lazyplan (`lpui`) — vX.Y.Z`) and the version-pinned
# asset URLs in README.md + site/index.html mirror it and are updated here.
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
sed -i.bak -E "s/lazyplan_[0-9]+\.[0-9]+\.[0-9]+-1_/lazyplan_${NEXT}-1_/g" README.md && rm README.md.bak
sed -i.bak -E "s/lazyplan-[0-9]+\.[0-9]+\.[0-9]+-1\./lazyplan-${NEXT}-1./g" README.md && rm README.md.bak
# Man page embeds the version (tests/test_help.py enforces it) — regenerate.
python3 tools/gen-man.py
if ! grep -q "lazyplan-tui $NEXT" docs/lpui.1; then
  echo "error: man page regen failed" >&2
  exit 1
fi
# Site mirrors: version-pinned release asset URLs, JSON-LD version, sitemap date.
if [[ -f site/index.html ]]; then
  sed -i.bak -E "s|/releases/download/v[0-9]+\.[0-9]+\.[0-9]+/|/releases/download/v${NEXT}/|g" site/index.html && rm site/index.html.bak
  sed -i.bak -E "s/lazyplan_[0-9]+\.[0-9]+\.[0-9]+-1_/lazyplan_${NEXT}-1_/g" site/index.html && rm site/index.html.bak
  sed -i.bak -E "s/lazyplan-[0-9]+\.[0-9]+\.[0-9]+-1\./lazyplan-${NEXT}-1./g" site/index.html && rm site/index.html.bak
  sed -i.bak -E "s/\"version\": \"[0-9]+\.[0-9]+\.[0-9]+\"/\"version\": \"$NEXT\"/" site/index.html && rm site/index.html.bak
  sed -i.bak -E "s/\"softwareVersion\": \"[0-9]+\.[0-9]+\.[0-9]+\"/\"softwareVersion\": \"$NEXT\"/" site/index.html && rm site/index.html.bak
fi
if [[ -f site/package.json ]]; then
  sed -i.bak -E "s/^  \"version\": \"[0-9]+\.[0-9]+\.[0-9]+\"(,?)$/  \"version\": \"$NEXT\"\1/" site/package.json && rm site/package.json.bak
fi
if [[ -f site/public/sitemap.xml ]]; then
  TODAY="$(date +%F)"
  sed -i.bak -E "s|<lastmod>[0-9]{4}-[0-9]{2}-[0-9]{2}</lastmod>|<lastmod>$TODAY</lastmod>|" site/public/sitemap.xml && rm site/public/sitemap.xml.bak
fi
if ! grep -q "^version = \"$NEXT\"$" pyproject.toml; then
  echo "error: pyproject update failed" >&2
  exit 1
fi
if ! head -1 README.md | grep -q " — v$NEXT$"; then
  echo "error: README header update failed" >&2
  exit 1
fi

git add pyproject.toml README.md docs/
if [[ -f site/index.html ]]; then git add site/index.html site/public/sitemap.xml site/package.json; fi
git commit -m "release v$NEXT"
git tag -a "v$NEXT" -m "lazyplan v$NEXT"
echo "committed + tagged v$NEXT"
if [[ $PUSH -eq 1 ]]; then
  git push origin HEAD
  git push origin "v$NEXT"
fi
