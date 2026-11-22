#!/usr/bin/env bash
# Tool-install smoke: install lazyplan with uv and pipx in throwaway homes,
# prove both commands and the detected method, then exercise the upgrade path.
# Fails instead of skipping when uv or pipx is missing.
# Usage:
#   ./tools/check-tool-install.sh [--version X.Y.Z] [--from-version X.Y.Z]
#   ./tools/check-tool-install.sh --from-previous   # upgrade from the prior PyPI release
#   ./tools/check-tool-install.sh --wheel dist/lazyplan_tui-X.Y.Z-py3-none-any.whl
#   VERSION=0.51.1 ./tools/check-tool-install.sh
# Without --version the latest PyPI release is used. --wheel proves a local
# build instead and skips the PyPI upgrade exercise.
# Requires: uv, pipx, python3, curl (curl only for the PyPI paths).
set -euo pipefail
cd "$(dirname "$0")/.."

PKG="lazyplan-tui"
VERSION="${VERSION:-}"
FROM_VERSION=""
FROM_PREVIOUS=0
WHEEL=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --version=*) VERSION="${1#--version=}"; shift ;;
    --version) VERSION="${2:-}"; shift 2 ;;
    --from-version=*) FROM_VERSION="${1#--from-version=}"; shift ;;
    --from-version) FROM_VERSION="${2:-}"; shift 2 ;;
    --from-previous) FROM_PREVIOUS=1; shift ;;
    --wheel=*) WHEEL="${1#--wheel=}"; shift ;;
    --wheel) WHEEL="${2:-}"; shift 2 ;;
    -h|--help)
      sed -n '2,12p' "$0"; exit 0 ;;
    -*)
      echo "error: unknown flag '$1'" >&2; exit 2 ;;
    *)
      echo "error: unknown arg '$1'" >&2; exit 2 ;;
  esac
done

for tool in uv pipx python3; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "error: $tool is required for the tool-install smoke" >&2
    exit 2
  fi
done
if [[ -z "$WHEEL" ]] && ! command -v curl >/dev/null 2>&1; then
  echo "error: curl is required to resolve PyPI releases" >&2
  exit 2
fi
if [[ -n "$WHEEL" && ! -f "$WHEEL" ]]; then
  echo "error: wheel not found: $WHEEL" >&2
  exit 1
fi

latest_version() {
  curl -fsSL "https://pypi.org/pypi/$PKG/json" |
    python3 -c 'import json, sys; print(json.load(sys.stdin)["info"]["version"])'
}

previous_version() {
  curl -fsSL "https://pypi.org/pypi/$PKG/json" |
    python3 -c '
import json, sys

target = tuple(map(int, sys.argv[1].split(".")))
releases = [
    version
    for version in json.load(sys.stdin)["releases"]
    if len(version.split(".")) == 3 and all(part.isdigit() for part in version.split("."))
]
older = [version for version in releases if tuple(map(int, version.split("."))) < target]
print(max(older, key=lambda version: tuple(map(int, version.split(".")))) if older else "")
' "$1"
}

if [[ -z "$WHEEL" ]]; then
  if [[ -z "$VERSION" ]]; then
    VERSION="$(latest_version)"
  fi
  if ! [[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "error: cannot resolve version (got '$VERSION')" >&2
    exit 1
  fi
  if [[ "$FROM_PREVIOUS" -eq 1 ]]; then
    FROM_VERSION="$(previous_version "$VERSION")"
    if [[ -z "$FROM_VERSION" ]]; then
      echo "error: no release older than $VERSION on PyPI" >&2
      exit 1
    fi
  fi
fi

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

export UV_TOOL_DIR="$WORK/uv/tools"
export UV_TOOL_BIN_DIR="$WORK/uv/bin"
export PIPX_HOME="$WORK/pipx/home"
export PIPX_BIN_DIR="$WORK/pipx/bin"
mkdir -p "$UV_TOOL_BIN_DIR" "$PIPX_BIN_DIR"

if [[ -n "$WHEEL" ]]; then
  echo "== uv tool install $WHEEL =="
  uv tool install --quiet "$WHEEL"
else
  echo "== uv tool install $PKG==$VERSION =="
  uv tool install --quiet "$PKG==$VERSION"
fi
UV_LPUI="$UV_TOOL_BIN_DIR/lpui"
test -x "$UV_LPUI"
test -x "$UV_TOOL_BIN_DIR/lazyplan"
if [[ -z "$WHEEL" ]]; then
  [[ "$("$UV_LPUI" --version)" == "$VERSION" ]]
else
  VERSION="$("$UV_LPUI" --version)"
fi

echo "== uv method detection =="
UV_DIAG="$("$UV_LPUI" upgrade --diagnose --json)"
python3 - "$UV_DIAG" <<'PY'
import json
import sys

data = json.loads(sys.argv[1])
if data["method"] != "uv" or not data["upgradeable"]:
    raise SystemExit(f"uv install not detected: {data['method']} {data['upgradeable']}")
PY

if [[ -n "$WHEEL" ]]; then
  echo "== pipx install $WHEEL =="
  pipx install --quiet "$WHEEL"
else
  echo "== pipx install $PKG==$VERSION =="
  pipx install --quiet "$PKG==$VERSION"
fi
PIPX_LPUI="$PIPX_BIN_DIR/lpui"
test -x "$PIPX_LPUI"
test -x "$PIPX_BIN_DIR/lazyplan"
[[ "$("$PIPX_LPUI" --version)" == "$VERSION" ]]

echo "== pipx method detection =="
PIPX_DIAG="$("$PIPX_LPUI" upgrade --diagnose --json)"
python3 - "$PIPX_DIAG" <<'PY'
import json
import sys

data = json.loads(sys.argv[1])
if data["method"] != "pipx" or not data["upgradeable"]:
    raise SystemExit(f"pipx install not detected: {data['method']} {data['upgradeable']}")
PY

if [[ -n "$WHEEL" ]]; then
  echo "wheel smoke only: PyPI upgrade exercise skipped"
elif [[ -n "$FROM_VERSION" ]]; then
  echo "== upgrade uv from $FROM_VERSION to $VERSION =="
  uv tool install --quiet "$PKG==$FROM_VERSION" --force
  [[ "$("$UV_LPUI" --version)" == "$FROM_VERSION" ]]
  "$UV_LPUI" upgrade
  [[ "$("$UV_LPUI" --version)" == "$VERSION" ]]

  echo "== upgrade pipx from $FROM_VERSION to $VERSION =="
  pipx install --quiet "$PKG==$FROM_VERSION" --force
  [[ "$("$PIPX_LPUI" --version)" == "$FROM_VERSION" ]]
  "$PIPX_LPUI" upgrade
  [[ "$("$PIPX_LPUI" --version)" == "$VERSION" ]]
else
  echo "== upgrade is a guarded no-op at the latest release =="
  "$UV_LPUI" upgrade
  "$PIPX_LPUI" upgrade
fi

echo "tool-install smoke green (v$VERSION)"
