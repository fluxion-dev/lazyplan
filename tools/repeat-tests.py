"""Run the unittest suite repeatedly in a seeded, shuffled order.

Each pass is a fresh interpreter, so module state cannot leak between passes;
the pass shuffles every test (not just the module) and honors the time-boxed
quarantine file. The runner is stdlib-only.

Usage:
  python tools/repeat-tests.py [--times 3] [--seed 0] [--no-tui] [--list]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import random
import subprocess
import sys
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
QUARANTINE = ROOT / "tests" / "quarantine.json"
SKIP_NO_TUI = ("tests.presentation", "tests.setup.test_setup_pty")


def all_tests(no_tui: bool = False) -> list[unittest.Test]:
    """Every discovered test, flattened and filtered."""
    loader = unittest.TestLoader()
    discovered = loader.discover(str(ROOT / "tests"), top_level_dir=str(ROOT))

    def walk(suite: unittest.TestSuite) -> list[unittest.Test]:
        found: list[unittest.Test] = []
        for item in suite:
            if isinstance(item, unittest.TestSuite):
                found.extend(walk(item))
            else:
                found.append(item)
        return found

    tests = walk(discovered)
    if no_tui:
        tests = [test for test in tests if not test.id().startswith(SKIP_NO_TUI)]
    return tests


def load_quarantine(path: Path = QUARANTINE) -> list[dict[str, Any]]:
    """Load and validate the quarantine file; raise ValueError when invalid."""
    if not path.is_file():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("tests"), list):
        raise ValueError(f"{path}: expected an object with a tests list")
    entries: list[dict[str, Any]] = []
    today = dt.date.today()
    for index, entry in enumerate(raw["tests"]):
        if not isinstance(entry, dict):
            raise ValueError(f"{path}: entry {index} must be an object")
        missing = [key for key in ("id", "task", "reason", "expires") if not entry.get(key)]
        if missing:
            raise ValueError(f"{path}: entry {index} needs {', '.join(missing)}")
        if not isinstance(entry["task"], int) or entry["task"] < 1:
            raise ValueError(f"{path}: entry {index} task must be a positive id")
        try:
            expires = dt.date.fromisoformat(str(entry["expires"]))
        except ValueError as exc:
            raise ValueError(f"{path}: entry {index} expires must be YYYY-MM-DD") from exc
        if expires <= today:
            raise ValueError(f"{path}: entry {index} expired on {expires}")
        entries.append(dict(entry))
    return entries


def shuffled(tests: list[unittest.Test], seed: int, attempt: int) -> list[unittest.Test]:
    """One deterministic shuffle for a seed and pass number."""
    order = list(tests)
    random.Random(seed + attempt).shuffle(order)
    return order


def main(argv: list[str] | None = None) -> int:
    """Run the passes and stop on the first failure."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--times", type=int, default=3)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--no-tui", action="store_true")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--worker", type=int, default=-1, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.worker >= 0:
        return _worker(args.worker, args.no_tui)
    try:
        quarantine = load_quarantine()
    except (OSError, ValueError) as exc:
        print(f"quarantine error: {exc}", file=sys.stderr)
        return 2
    if args.list:
        for entry in quarantine:
            print(f"quarantine {entry['id']} until {entry['expires']}")
        for test in all_tests(no_tui=args.no_tui):
            print(test.id())
        return 0
    if not all_tests(no_tui=args.no_tui):
        print("no tests found", file=sys.stderr)
        return 2
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(
        [str(ROOT / "src"), environment.get("PYTHONPATH", "")]
    ).rstrip(os.pathsep)
    for attempt in range(args.times):
        seed = args.seed + attempt
        print(f"pass {attempt + 1}/{args.times} (seed {seed})", flush=True)
        command = [sys.executable, str(ROOT / "tools" / "repeat-tests.py"), "--worker", str(seed)]
        if args.no_tui:
            command.append("--no-tui")
        result = subprocess.run(command, cwd=ROOT, env=environment, check=False)
        if result.returncode:
            print(f"reproduce: PYTHONPATH=src {' '.join(command)}", file=sys.stderr)
            return result.returncode or 1
    print(f"{args.times} pass(es) complete", flush=True)
    return 0


def _worker(seed: int, no_tui: bool) -> int:
    """Run one shuffled pass in this process."""
    try:
        quarantine = {entry["id"] for entry in load_quarantine()}
    except (OSError, ValueError) as exc:
        print(f"quarantine error: {exc}", file=sys.stderr)
        return 2
    tests = [test for test in all_tests(no_tui=no_tui) if test.id() not in quarantine]
    result = unittest.TextTestRunner(verbosity=1).run(unittest.TestSuite(shuffled(tests, seed, 0)))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
