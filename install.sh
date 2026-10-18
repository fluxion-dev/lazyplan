#!/bin/sh
# lazyplan installer — one script for Linux system + user installs.
#   curl -fsSL https://github.com/fluxion-dev/lazyplan/releases/latest/download/install.sh | sh
#   ./install.sh [--version X.Y.Z] [--method auto|rpm|deb|pipx|venv] [--prefix ~/.local] [--uninstall]
#
# Methods:
#   rpm  - sudo dnf/yum/zypper install of lazyplan-VERSION-1.<arch>.rpm (Fedora/RHEL/openSUSE)
#   deb  - sudo apt install of lazyplan_VERSION_<arch>.deb (Debian/Ubuntu)
#   pipx - pipx install lazyplan-tui (isolated venv, preferred user install)
#   venv - python3 -m venv + pip install + symlinks (no pipx required)
#   auto - rpm on rpm distros, deb on deb distros, else pipx if present, else venv
# POSIX sh only. Never writes as root except via the system package manager.
set -eu

REPO="fluxion-dev/lazyplan"
PYPI_PKG="lazyplan-tui"
BIN1="lpui"
BIN2="lazyplan"

VERSION="${LAZYPLAN_VERSION:-}"
METHOD="auto"
PREFIX="${HOME:-$HOME}/.local"
UNINSTALL=0

usage() {
  sed -n '2,12p' "$0"
  echo ""
  echo "options:"
  echo "  --version X.Y.Z   pin version (default: latest GitHub release)"
  echo "  --method M        auto|rpm|deb|pipx|venv (default: auto)"
  echo "  --prefix DIR      user-install prefix for pipx/venv (default: ~/.local)"
  echo "  --uninstall       remove lazyplan (tries rpm/dnf, apt, pipx, venv, prefix links)"
  echo "  -h, --help        this help"
}

log() { printf '%s\n' "$*"; }
err() { printf 'error: %s\n' "$*" >&2; }

while [ $# -gt 0 ]; do
  case "$1" in
    -h|--help) usage; exit 0 ;;
    --uninstall) UNINSTALL=1; shift ;;
    --version) VERSION="${2:-}"; shift 2 ;;
    --version=*) VERSION="${1#--version=}"; shift ;;
    --method) METHOD="${2:-}"; shift 2 ;;
    --method=*) METHOD="${1#--method=}"; shift ;;
    --prefix) PREFIX="${2:-}"; shift 2 ;;
    --prefix=*) PREFIX="${1#--prefix=}"; shift ;;
    --*) err "unknown flag $1"; usage >&2; exit 2 ;;
    *) err "unknown arg $1"; usage >&2; exit 2 ;;
  esac
done

case "$METHOD" in
  auto|rpm|deb|pipx|venv) ;;
  *) err "--method must be auto|rpm|deb|pipx|venv"; exit 2 ;;
esac

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || { err "need '$1' in PATH"; return 1; }
}

machine_arch() {
  case "$(uname -m)" in
    x86_64) printf 'amd64' ;;
    aarch64|arm64) printf 'arm64' ;;
    *) err "unsupported arch $(uname -m) (amd64/arm64 only)"; exit 1 ;;
  esac
}

resolve_latest() {
  # Follow the /releases/latest redirect to learn the tag (no jq needed).
  url="$(curl -fsSL -o /dev/null -w '%{url_effective}' "https://github.com/$REPO/releases/latest" 2>/dev/null || true)"
  tag="${url##*/tag/}"
  case "$tag" in
    v*.*.*) printf '%s' "${tag#v}" ;;
    *) printf '' ;;
  esac
}

do_uninstall() {
  log "uninstalling lazyplan..."
  if command -v rpm >/dev/null 2>&1 && rpm -q lazyplan >/dev/null 2>&1; then
    if [ "$(id -u)" -eq 0 ]; then SUDO=""; elif command -v sudo >/dev/null 2>&1; then SUDO="sudo"; else SUDO=""; fi
    if command -v dnf >/dev/null 2>&1; then ${SUDO:+$SUDO }dnf remove -y lazyplan || true
    elif command -v yum >/dev/null 2>&1; then ${SUDO:+$SUDO }yum remove -y lazyplan || true
    elif command -v zypper >/dev/null 2>&1; then ${SUDO:+$SUDO }zypper remove -y lazyplan || true
    elif command -v rpm >/dev/null 2>&1; then ${SUDO:+$SUDO }rpm -e lazyplan || true
    fi
  fi
  if command -v dpkg >/dev/null 2>&1 && dpkg -s lazyplan >/dev/null 2>&1; then
    if [ "$(id -u)" -eq 0 ]; then SUDO=""; elif command -v sudo >/dev/null 2>&1; then SUDO="sudo"; else SUDO=""; fi
    if [ -n "${SUDO:-}" ] || [ "$(id -u)" -eq 0 ]; then ${SUDO:+$SUDO }apt remove -y lazyplan || true; fi
  fi
  if command -v pipx >/dev/null 2>&1; then pipx uninstall "$PYPI_PKG" || true; fi
  rm -rf "$PREFIX/share/lazyplan-venv" "$PREFIX/lib/lazyplan-venv"
  rm -f "$PREFIX/bin/$BIN1" "$PREFIX/bin/$BIN2" "$PREFIX/bin/lp"
  rm -f "$PREFIX/share/man/man1/$BIN1.1" "$PREFIX/share/man/man1/$BIN2.1"
  rm -f "$PREFIX/share/bash-completion/completions/$BIN1" "$PREFIX/share/bash-completion/completions/$BIN2"
  rm -f "$PREFIX/share/zsh/site-functions/_$BIN1" "$PREFIX/share/zsh/site-functions/_$BIN2"
  log "done."
}

if [ "$UNINSTALL" -eq 1 ]; then do_uninstall; exit 0; fi

if [ -z "$VERSION" ]; then
  VERSION="$(resolve_latest)"
  if [ -z "$VERSION" ]; then
    err "cannot resolve latest release (network?). Pass --version X.Y.Z."
    exit 1
  fi
fi
case "$VERSION" in
  v*) VERSION="${VERSION#v}" ;;
esac
log "lazyplan v$VERSION (method: $METHOD)"

if [ "$METHOD" = "auto" ]; then
  if [ -f /etc/fedora-release ] || [ -f /etc/redhat-release ] || [ -f /etc/SuSE-release ]; then
    METHOD="rpm"
  elif [ -f /etc/debian_version ]; then
    METHOD="deb"
  elif command -v pipx >/dev/null 2>&1; then
    METHOD="pipx"
  else
    METHOD="venv"
  fi
  log "auto -> $METHOD"
fi

install_extras_from_repo_or_web() {
  # $1 = installed lpui binary (for completions). Man pages: prefer local docs/, else GitHub raw.
  _bin="$1"
  mkdir -p "$PREFIX/share/man/man1" "$PREFIX/share/bash-completion/completions" "$PREFIX/share/zsh/site-functions"
  _found=0
  for _d in "$(dirname "$0")/docs" "./docs" "$PREFIX/share/doc/lazyplan"; do
    if [ -f "$_d/lpui.1" ]; then
      cp "$_d/lpui.1" "$PREFIX/share/man/man1/lpui.1"
      cp "$_d/lazyplan.1" "$PREFIX/share/man/man1/lazyplan.1" 2>/dev/null || printf '.so lpui.1\n' > "$PREFIX/share/man/man1/lazyplan.1"
      _found=1; break
    fi
  done
  if [ "$_found" -eq 0 ] && command -v curl >/dev/null 2>&1; then
    curl -fsSL "https://raw.githubusercontent.com/$REPO/v$VERSION/docs/lpui.1" -o "$PREFIX/share/man/man1/lpui.1" || true
    curl -fsSL "https://raw.githubusercontent.com/$REPO/v$VERSION/docs/lazyplan.1" -o "$PREFIX/share/man/man1/lazyplan.1" || true
  fi
  if [ -x "$_bin" ] || command -v "$_bin" >/dev/null 2>&1; then
    "$_bin" completion --shell bash > "$PREFIX/share/bash-completion/completions/lpui" 2>/dev/null || true
    cp "$PREFIX/share/bash-completion/completions/lpui" "$PREFIX/share/bash-completion/completions/lazyplan" 2>/dev/null || true
    "$_bin" completion --shell zsh > "$PREFIX/share/zsh/site-functions/_lpui" 2>/dev/null || true
    cp "$PREFIX/share/zsh/site-functions/_lpui" "$PREFIX/share/zsh/site-functions/_lazyplan" 2>/dev/null || true
  fi
}

do_pipx() {
  need_cmd pipx
  need_cmd python3
  if pipx list --short 2>/dev/null | grep -q "^$PYPI_PKG "; then
    log "pipx upgrade $PYPI_PKG..."
    pipx upgrade "$PYPI_PKG" --pip-args "==$VERSION" || pipx install "$PYPI_PKG==$VERSION" --force
  else
    log "pipx install $PYPI_PKG==$VERSION..."
    pipx install "$PYPI_PKG==$VERSION"
  fi
  # 0.7.0 shipped `lp`; >=0.8.0 ships `lpui` + `lazyplan`. Use what exists.
  _cli=""
  for _b in "$BIN1" "$BIN2" lp; do
    if command -v "$_b" >/dev/null 2>&1; then _cli="$_b"; break; fi
  done
  if [ -n "$_cli" ]; then install_extras_from_repo_or_web "$_cli"; fi
  log "installed. Ensure ~/.local/bin is on PATH: export PATH=\"\$HOME/.local/bin:\$PATH\""
  if [ -n "$_cli" ]; then "$_cli" --help >/dev/null && log "OK: $_cli --help works"; fi
}

do_venv() {
  need_cmd python3
  need_cmd curl
  VENV="$PREFIX/share/lazyplan-venv"
  log "venv install into $VENV..."
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install --quiet --upgrade pip
  "$VENV/bin/pip" install --quiet "$PYPI_PKG==$VERSION"
  mkdir -p "$PREFIX/bin"
  _cli=""
  for _b in "$BIN1" "$BIN2" lp; do
    if [ -x "$VENV/bin/$_b" ]; then
      ln -sf "$VENV/bin/$_b" "$PREFIX/bin/$_b"
      if [ -z "$_cli" ]; then _cli="$PREFIX/bin/$_b"; fi
    fi
  done
  if [ -z "$_cli" ]; then err "pip install succeeded but no lpui/lazyplan/lp entry point found"; exit 1; fi
  install_extras_from_repo_or_web "$_cli"
  log "installed to $PREFIX/bin. Ensure $PREFIX/bin is on PATH."
  "$_cli" --help >/dev/null && log "OK: $_cli --help works"
}

do_rpm() {
  need_cmd curl
  ARCH="$(machine_arch)"
  case "$ARCH" in
    amd64) RPMARCH="x86_64" ;;
    arm64) RPMARCH="aarch64" ;;
  esac
  FILE="lazyplan-$VERSION-1.$RPMARCH.rpm"
  URL="https://github.com/$REPO/releases/download/v$VERSION/$FILE"
  TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT INT TERM
  log "downloading $URL..."
  curl -fsSL "$URL" -o "$TMP/$FILE"
  if [ "$(id -u)" -eq 0 ]; then SUDO=""
  elif command -v sudo >/dev/null 2>&1; then SUDO="sudo"
  else err "need root (or sudo) to install rpm"; exit 1
  fi
  if command -v dnf >/dev/null 2>&1; then ${SUDO:+$SUDO }dnf install -y "$TMP/$FILE"
  elif command -v yum >/dev/null 2>&1; then ${SUDO:+$SUDO }yum install -y "$TMP/$FILE"
  elif command -v zypper >/dev/null 2>&1; then ${SUDO:+$SUDO }zypper --no-confirm install "$TMP/$FILE"
  else ${SUDO:+$SUDO }rpm -Uvh "$TMP/$FILE"
  fi
  lpui --help >/dev/null && log "OK: lpui --help works"
}

do_deb() {
  need_cmd curl
  ARCH="$(machine_arch)"
  FILE="lazyplan_${VERSION}-1_${ARCH}.deb"
  URL="https://github.com/$REPO/releases/download/v$VERSION/$FILE"
  TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT INT TERM
  log "downloading $URL..."
  curl -fsSL "$URL" -o "$TMP/$FILE"
  if [ "$(id -u)" -eq 0 ]; then SUDO=""
  elif command -v sudo >/dev/null 2>&1; then SUDO="sudo"
  else err "need root (or sudo) to install deb"; exit 1
  fi
  if command -v apt >/dev/null 2>&1; then ${SUDO:+$SUDO }apt install -y "$TMP/$FILE"
  else ${SUDO:+$SUDO }dpkg -i "$TMP/$FILE"
  fi
  lpui --help >/dev/null && log "OK: lpui --help works"
}

case "$METHOD" in
  pipx) do_pipx ;;
  venv) do_venv ;;
  rpm) do_rpm ;;
  deb) do_deb ;;
esac
