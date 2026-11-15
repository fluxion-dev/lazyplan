"""Run the unittest modules repeatedly in a seeded, shuffled order.

The runner is deliberately stdlib-only. Each pass is a fresh interpreter, so
module state cannot leak between passes; the module order is shuffled per pass
so a test that depends on a neighbor fails with a reproducible command.

Usage:
  python tools/repeat-tests.py [--times 3] [--seed 0] [--no-tui] [--list]
"""

from __future__ import annotations

import argparse
import os
import random
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_NO_TUI = ("tests.presentation", "tests.setup.test_setup_pty")


def modules(root: Path = ROOT, no_tui: bool = False) -> list[str]:
    """Every dotted unittest module under ``tests/``."""
    names: list[str] = []
    for path in sorted((root / "tests").rglob("test_*.py")):
        relative = path.relative_to(root).with_suffix("")
        name = ".".join(relative.parts)
        if no_tui and name.startswith(SKIP_NO_TUI):
            continue
        names.append(name)
    return names


def shuffled(names: list[str], seed: int, attempt: int) -> list[str]:
    """One deterministic shuffle for a seed and pass number."""
    order = list(names)
    random.Random(seed + attempt).shuffle(order)
    return order


def command(names: list[str], seed: int, attempt: int) -> list[str]:
    """The subprocess command for one pass."""
    return [sys.executable, "-m", "unittest", "-q", *shuffled(names, seed, attempt)]


def main(argv: list[str] | None = None) -> int:
    """Run the passes and stop on the first failure."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--times", type=int, default=3)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--no-tui", action="store_true")
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args(argv)
    names = modules(no_tui=args.no_tui)
    if args.list:
        print("\n".join(names))
        return 0
    if not names:
        print("no test modules found", file=sys.stderr)
        return 2
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(
        [str(ROOT / "src"), environment.get("PYTHONPATH", "")]
    ).rstrip(os.pathsep)
    for attempt in range(args.times):
        argv_attempt = command(names, args.seed, attempt)
        print(f"pass {attempt + 1}/{args.times} (seed {args.seed + attempt})", flush=True)
        result = subprocess.run(argv_attempt, cwd=ROOT, env=environment, check=False)
        if result.returncode:
            print(
                f"reproduce: PYTHONPATH=src {' '.join(argv_attempt)}",
                file=sys.stderr,
            )
            return result.returncode or 1
    print(f"{args.times} pass(es) complete", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
