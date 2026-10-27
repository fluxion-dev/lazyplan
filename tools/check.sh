#!/usr/bin/env bash
# lazyplan gates: lint + format + types + tests (both interpreters).
# Usage: ./tools/check.sh   (Linux, macOS, or Git Bash on Windows)
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
echo "== ruff check =="
"$VENV_BIN"/ruff check src tests
echo "== ruff format --check =="
"$VENV_BIN"/ruff format --check src tests
echo "== mypy (strict incl. untyped defs) =="
"$VENV_BIN"/mypy src
echo "== vulture (no dead code outside the allowlist) =="
"$VENV_BIN"/python -m vulture src/ tools/vulture_allowlist.py
echo "== xenon (no block worse than C) =="
"$VENV_BIN"/python -m xenon --max-absolute C src
echo "== man page in sync =="
"$VENV_BIN"/python tools/gen-man.py --check
echo "== site discoverability =="
"$SYS_PY" tools/check-site.py
echo "== clean install smoke =="
./tools/check-install.sh
echo "== unittest (system python, stdlib only) =="
PYTHONPATH=src "$SYS_PY" -m unittest discover -s tests
echo "== unittest (venv python, with textual) =="
"$VENV_BIN"/python -m unittest discover -s tests
echo "== performance budgets =="
"$VENV_BIN"/python tools/perf_bench.py --check
echo "ALL GATES GREEN"
