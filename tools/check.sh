#!/usr/bin/env bash
# lazyplan gates: lint + format + types + tests (both interpreters).
# Usage: ./tools/check.sh
set -euo pipefail
cd "$(dirname "$0")/.."
VENV_BIN="${VENV_BIN:-.venv/bin}"
echo "== ruff check =="
"$VENV_BIN"/ruff check src tests
echo "== ruff format --check =="
"$VENV_BIN"/ruff format --check src tests
echo "== mypy (strict incl. untyped defs) =="
"$VENV_BIN"/mypy src
echo "== man page in sync =="
"$VENV_BIN"/python tools/gen-man.py --check
echo "== unittest (system python, stdlib only) =="
PYTHONPATH=src python3 -m unittest discover -s tests
echo "== unittest (venv python, with textual) =="
"$VENV_BIN"/python -m unittest discover -s tests
echo "ALL GATES GREEN"
