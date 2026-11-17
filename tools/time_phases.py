#!/usr/bin/env python3
"""Time the site build, screenshot capture, and the full gate.

Usage:
  .venv/bin/python tools/time_phases.py             # every phase that can run
  .venv/bin/python tools/time_phases.py --phase gate
  .venv/bin/python tools/time_phases.py --repeat 2

A phase that cannot run here (no node/npm, no site/node_modules) is reported
as skipped instead of failing, so the numbers stay comparable across hosts.
Capture writes to a throwaway directory; nothing tracked is modified.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PHASES = ("site", "prerender", "capture", "ux", "gate")


def _site_ready() -> str | None:
    """Reason the site phase cannot run, or None when it can."""
    if shutil.which("npm") is None:
        return "npm not installed"
    if not (ROOT / "site" / "node_modules").is_dir():
        return "run npm ci in site/ first"
    return None


def _phase(name: str, work: Path) -> list[str] | None:
    """The command for one phase, or None when the host cannot run it."""
    if name == "site":
        reason = _site_ready()
        if reason is not None:
            print(f"{name:<10} skipped ({reason})")
            return None
        # `npm run build` runs tsc, the client build, the SSR build, then the
        # prerender script; time it as one command rather than guessing splits.
        return ["npm", "run", "build"]
    if name == "capture":
        return [
            sys.executable,
            str(ROOT / "tools" / "capture-screens.py"),
            "--out",
            str(work / "capture"),
            "--no-og",
        ]
    if name == "ux":
        return [
            sys.executable,
            str(ROOT / "tools" / "capture-ux-review.py"),
            "--out",
            str(work / "ux"),
        ]
    if name == "prerender":
        if not (ROOT / "site" / ".ssr").is_dir():
            print("prerender   skipped (run the site phase first)")
            return None
        if shutil.which("node") is None:
            print("prerender   skipped (node not installed)")
            return None
        return ["node", "scripts/prerender.mjs"]
    return [str(ROOT / "tools" / "check.sh")]


def _time(command: list[str], cwd: Path) -> float:
    start = time.perf_counter()
    subprocess.run(command, cwd=cwd, check=True, timeout=3_600)
    return time.perf_counter() - start


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--phase",
        action="append",
        choices=PHASES,
        default=[],
        help="time only this phase (repeatable; default: all)",
    )
    parser.add_argument("--repeat", type=int, default=1, help="runs per phase")
    args = parser.parse_args(argv)
    names = args.phase or list(PHASES)
    rows: list[tuple[str, float | None, str]] = []
    with tempfile.TemporaryDirectory(prefix="lazyplan-phases-") as tmp:
        work = Path(tmp)
        for name in names:
            command = _phase(name, work)
            if command is None:
                rows.append((name, None, "skipped"))
                continue
            cwd = ROOT / "site" if name in ("site", "prerender") else ROOT
            best = min(_time(command, cwd) for _ in range(max(1, args.repeat)))
            rows.append((name, best, "s"))
    print(f"{'phase':<10} {'seconds':>8}  note")
    for name, seconds, note in rows:
        shown = "-" if seconds is None else f"{seconds:.2f}"
        print(f"{name:<10} {shown:>8}  {note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
