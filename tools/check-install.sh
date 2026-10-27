#!/usr/bin/env bash
# Clean-install smoke: build a wheel, install it into a throwaway venv, and
# prove both console scripts and the package import resolve from the install.
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ -z "${VENV_BIN:-}" ]]; then
  if [[ -d .venv/Scripts ]]; then VENV_BIN=.venv/Scripts; else VENV_BIN=.venv/bin; fi
fi
if [[ -z "${SYS_PY:-}" ]]; then
  for candidate in python3 python; do
    if "$candidate" -c "import sys" >/dev/null 2>&1; then SYS_PY="$candidate"; break; fi
  done
fi
: "${SYS_PY:?no working python3 or python on PATH}"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

echo "== build wheel =="
# Let pip honor pyproject's build requires; the gate venv may carry an older
# setuptools than the PEP 639 metadata needs.
"$VENV_BIN/python" -m pip wheel . --no-deps --quiet --wheel-dir "$WORK/wheel"

echo "== install wheel =="
"$SYS_PY" -m venv "$WORK/venv"
if [[ -d "$WORK/venv/Scripts" ]]; then VENV_BIN="$WORK/venv/Scripts"; else VENV_BIN="$WORK/venv/bin"; fi
"$VENV_BIN/python" -m pip install --no-deps --quiet "$WORK"/wheel/*.whl

echo "== console scripts =="
"$VENV_BIN/lpui" --version
"$VENV_BIN/lazyplan" --version

echo "== installed import =="
"$VENV_BIN/python" - "$WORK" <<'PY'
import pathlib
import sys

import lazyplan

path = pathlib.Path(lazyplan.__file__).resolve()
print(path)
if "site-packages" not in path.parts:
    raise SystemExit(f"lazyplan imported outside site-packages: {path}")
PY

echo "clean install smoke green"
