"""Fail on test patterns that leak state or synchronize with a sleep.

The scan is deliberately small: real-home access and raw sleeps are the two
patterns that caused recent flakes. Legitimate exceptions carry a reason in
``HOME_ALLOWLIST``; the suite tests both the findings and the allowlist.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOME_ALLOWLIST = {
    "tests/vcs/test_repo.py": "asserts home path resolution only; never writes there",
}
SLEEP_PATTERNS = ("time.sleep(", "asyncio.sleep(")
HOME_PATTERNS = ("Path.home()", "pathlib.Path.home()")


def scan(root: Path = ROOT) -> list[str]:
    """Return one finding per offending pattern in the test tree."""
    findings: list[str] = []
    for path in sorted((root / "tests").rglob("*.py")):
        relative = path.relative_to(root).as_posix()
        if relative == "tests/support/home.py":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for pattern in SLEEP_PATTERNS:
            if pattern in text:
                findings.append(f"{relative}: {pattern} is not a synchronization primitive")
        if relative in HOME_ALLOWLIST:
            continue
        for pattern in HOME_PATTERNS:
            if pattern in text:
                findings.append(f"{relative}: {pattern} touches the real home")
    return findings


def main(argv: list[str] | None = None) -> int:
    """Print findings and return a process status."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    findings = scan(args.root)
    for finding in findings:
        print(finding)
    if findings:
        print(f"{len(findings)} test hygiene finding(s)", file=sys.stderr)
        return 1
    print("test hygiene ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
