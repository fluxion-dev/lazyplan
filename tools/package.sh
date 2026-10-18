#!/usr/bin/env bash
# Build Linux system packages (.deb + .rpm) via nfpm.
# Layout: /usr/lib/lazyplan (vendored pip --target) + /usr/bin wrappers.
# Usage:
#   ./tools/package.sh [--version X.Y.Z] [--arch amd64|arm64] [--format deb|rpm|all] [--output dist/]
#   VERSION=0.8.0 ARCH=amd64 ./tools/package.sh
# Requires: python3 (>=3.11), pip, curl; nfpm (auto-installed via `go install` if missing).
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

VERSION=""
ARCH=""
FORMAT="all"
OUTPUT="dist"
NFPM_VERSION="${NFPM_VERSION:-v2.47.0}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --version=*) VERSION="${1#--version=}"; shift ;;
    --version) VERSION="${2:-}"; shift 2 ;;
    --arch=*) ARCH="${1#--arch=}"; shift ;;
    --arch) ARCH="${2:-}"; shift 2 ;;
    --format=*) FORMAT="${1#--format=}"; shift ;;
    --format) FORMAT="${2:-}"; shift 2 ;;
    --output=*) OUTPUT="${1#--output=}"; shift ;;
    --output) OUTPUT="${2:-}"; shift 2 ;;
    -h|--help)
      sed -n '2,9p' "$0"; exit 0 ;;
    -*)
      echo "error: unknown flag '$1'" >&2; exit 2 ;;
    *)
      if [[ "$1" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] && [[ -z "$VERSION" ]]; then
        VERSION="$1"
      else
        echo "error: unknown arg '$1'" >&2; exit 2
      fi
      shift
      ;;
  esac
done

if [[ -z "$VERSION" ]]; then
  VERSION="$(sed -n 's/^version = "\(.*\)"$/\1/p' pyproject.toml)"
fi
if ! [[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "error: cannot resolve version (got '$VERSION')" >&2; exit 1
fi
if [[ -z "$ARCH" ]]; then
  case "$(uname -m)" in
    x86_64) ARCH="amd64" ;;
    aarch64|arm64) ARCH="arm64" ;;
    *) echo "error: unsupported arch $(uname -m) (use --arch amd64|arm64)" >&2; exit 1 ;;
  esac
fi
if [[ "$ARCH" != "amd64" && "$ARCH" != "arm64" ]]; then
  echo "error: --arch must be amd64|arm64" >&2; exit 1
fi

NFPM_BIN="${NFPM_BIN:-$(command -v nfpm || true)}"
if [[ -z "$NFPM_BIN" ]]; then
  case "$(uname -m)" in
    x86_64) NFPM_ARCH="x86_64" ;;
    aarch64|arm64) NFPM_ARCH="arm64" ;;
    *) echo "error: unsupported arch for nfpm bootstrap" >&2; exit 1 ;;
  esac
  NFPM_TGZ="nfpm_${NFPM_VERSION#v}_Linux_${NFPM_ARCH}.tar.gz"
  NFPM_URL="https://github.com/goreleaser/nfpm/releases/download/${NFPM_VERSION}/${NFPM_TGZ}"
  if command -v go >/dev/null 2>&1; then
    echo "== installing nfpm $NFPM_VERSION via go =="
    GOBIN_TMP="$(mktemp -d)"
    GOBIN="$GOBIN_TMP" go install "github.com/goreleaser/nfpm/v2/cmd/nfpm@$NFPM_VERSION"
    NFPM_BIN="$GOBIN_TMP/nfpm"
  elif command -v curl >/dev/null 2>&1; then
    echo "== downloading nfpm $NFPM_VERSION =="
    NFPM_TMP="$(mktemp -d)"
    curl -fsSL "$NFPM_URL" -o "$NFPM_TMP/nfpm.tar.gz"
    tar -xzf "$NFPM_TMP/nfpm.tar.gz" -C "$NFPM_TMP" nfpm
    chmod +x "$NFPM_TMP/nfpm"
    NFPM_BIN="$NFPM_TMP/nfpm"
  else
    echo "error: nfpm not found. Install it:" >&2
    echo "  go install github.com/goreleaser/nfpm/v2/cmd/nfpm@$NFPM_VERSION" >&2
    echo "  or: curl -fsSL $NFPM_URL | tar xz nfpm" >&2
    exit 1
  fi
fi
"$NFPM_BIN" --version

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
STAGING="$WORK/staging"
mkdir -p "$STAGING/usr/lib" "$STAGING/usr/bin" \
  "$STAGING/usr/share/man/man1" "$STAGING/usr/share/doc/lazyplan" \
  "$STAGING/usr/share/bash-completion/completions" \
  "$STAGING/usr/share/zsh/site-functions" "$OUTPUT"

echo "== vendoring lazyplan $VERSION + deps into staging =="
python3 -m pip install --quiet --target "$STAGING/usr/lib/lazyplan" "."
clean_pycache() {
  find "$STAGING/usr/lib/lazyplan" -name "__pycache__" -type d -prune -exec rm -rf {} + 2>/dev/null || true
  find "$STAGING/usr/lib/lazyplan" -name "*.pyc" -delete 2>/dev/null || true
}
clean_pycache
# pip --target also drops data-file man pages under share/; we ship our own
# copies to /usr/share, so drop the vendored duplicate. Same for entry-point bin/.
rm -rf "$STAGING/usr/lib/lazyplan"/share "$STAGING/usr/lib/lazyplan"/bin "$STAGING/usr/lib/lazyplan"/pip* \
  "$STAGING/usr/lib/lazyplan"/setuptools* "$STAGING/usr/lib/lazyplan"/wheel* \
  "$STAGING/usr/lib/lazyplan"/pkg_resources 2>/dev/null || true

echo "== wrappers / docs / completions =="
install -m 0755 packaging/lpui-wrapper.sh "$STAGING/usr/bin/lpui"
install -m 0755 packaging/lpui-wrapper.sh "$STAGING/usr/bin/lazyplan"
cp docs/lpui.1 "$STAGING/usr/share/man/man1/lpui.1"
cp docs/lazyplan.1 "$STAGING/usr/share/man/man1/lazyplan.1"
cp README.md "$STAGING/usr/share/doc/lazyplan/README.md"
cp LICENSE "$STAGING/usr/share/doc/lazyplan/LICENSE"
PYTHONPATH="src:${PYTHONPATH:-}" python3 -m lazyplan completion --shell bash > "$STAGING/usr/share/bash-completion/completions/lpui"
cp "$STAGING/usr/share/bash-completion/completions/lpui" "$STAGING/usr/share/bash-completion/completions/lazyplan"
PYTHONPATH="src:${PYTHONPATH:-}" python3 -m lazyplan completion --shell zsh > "$STAGING/usr/share/zsh/site-functions/_lpui"
cp "$STAGING/usr/share/zsh/site-functions/_lpui" "$STAGING/usr/share/zsh/site-functions/_lazyplan"

echo "== smoke test (staging) =="
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$STAGING/usr/lib/lazyplan" python3 -m lazyplan --help >/dev/null
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$STAGING/usr/lib/lazyplan" python3 -m lazyplan list --help >/dev/null
clean_pycache
rm -rf "$STAGING/usr/lib/lazyplan"/share "$STAGING/usr/lib/lazyplan"/bin 2>/dev/null || true

echo "== nfpm build ($FORMAT, $ARCH) =="
render_cfg="$WORK/nfpm.yaml"
VERSION="$VERSION" ARCH="$ARCH" python3 - "$render_cfg" <<'EOF'
import os, sys
src = open("packaging/nfpm.yaml").read()
src = src.replace("${VERSION}", os.environ["VERSION"]).replace("${ARCH}", os.environ["ARCH"])
open(sys.argv[1], "w").write(src)
EOF

build_one() {
  local fmt="$1"
  local out="$OUTPUT"
  case "$out" in
    /*) : ;; # absolute, keep
    *) out="$REPO_ROOT/$out" ;;
  esac
  mkdir -p "$out"
  (cd "$WORK" && "$NFPM_BIN" package --config "$render_cfg" --packager "$fmt" --target "$out/")
}

case "$FORMAT" in
  deb) build_one deb ;;
  rpm) build_one rpm ;;
  all) build_one deb; build_one rpm ;;
  *) echo "error: --format must be deb|rpm|all" >&2; exit 2 ;;
esac

echo "== done =="
ls -la "$OUTPUT"/ | grep -E "lazyplan.*(deb|rpm)" || true
