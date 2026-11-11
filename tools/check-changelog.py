#!/usr/bin/env python3
"""Fail when the packaged changelog drifts from the root CHANGELOG.md."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "CHANGELOG.md"
PACKAGED = ROOT / "src" / "lazyplan" / "data" / "CHANGELOG.md"


def _label(path: Path) -> str:
    """A repo-relative label when possible, else the path itself."""
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def main() -> int:
    """Compare the root changelog with the copy shipped in the package."""
    if not PACKAGED.is_file():
        print(
            f"error: missing {_label(PACKAGED)}; "
            "run: cp CHANGELOG.md src/lazyplan/data/CHANGELOG.md",
            file=sys.stderr,
        )
        return 1
    if SOURCE.read_bytes() != PACKAGED.read_bytes():
        print(
            f"error: {_label(PACKAGED)} is stale; "
            "run: cp CHANGELOG.md src/lazyplan/data/CHANGELOG.md",
            file=sys.stderr,
        )
        return 1
    print("changelog ok: packaged copy matches CHANGELOG.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
