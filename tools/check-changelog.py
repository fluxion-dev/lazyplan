#!/usr/bin/env python3
"""Check release headings and keep the packaged changelog in sync.

Usage:
  python3 tools/check-changelog.py
  python3 tools/check-changelog.py --stamp 0.41.1

The gate accepts an optional ``## Unreleased`` section and versioned headings
written as ``## vX.Y.Z — YYYY-MM-DD``. It fails on an undated release heading,
a duplicate or out-of-order version, an empty ``## Unreleased`` section, or a
packaged copy that differs from the root changelog.

``--stamp`` replaces the single ``## Unreleased`` heading with the next version
and today's date, then writes both the root and packaged copies.
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "CHANGELOG.md"
PACKAGED = ROOT / "src" / "lazyplan" / "data" / "CHANGELOG.md"

_HEADING = re.compile(r"^##\s+(.*)$")
_VERSION = re.compile(
    r"^## v(\d+)\.(\d+)\.(\d+) — (\d{4}-\d{2}-\d{2})$",
)
_PLAIN_VERSION = re.compile(r"^\d+\.\d+\.\d+$")
_SECTION = re.compile(r"^### (Added|Changed|Fixed)\s*$")
_UNRELEASED = "## Unreleased"
_EARLIER = "## Earlier releases"


def _label(path: Path) -> str:
    """A repo-relative label when possible, else the path itself."""
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _unreleased_errors(lines: list[str], start: int, end: int) -> list[str]:
    """Validate the body of one ``## Unreleased`` section."""
    body = lines[start:end]
    if not any(line.strip() for line in body):
        return [f"{_UNRELEASED} section is empty"]
    errors = []
    if not any(_SECTION.match(line) for line in body):
        errors.append(f"{_UNRELEASED} section needs an Added, Changed, or Fixed heading")
    if not any(line.strip() and not line.startswith("#") for line in body):
        errors.append(f"{_UNRELEASED} section has no entries")
    return errors


def check_text(text: str) -> list[str]:
    """Return every release-heading problem in *text*."""
    lines = text.splitlines()
    headings = [
        (index, match.group(1))
        for index, line in enumerate(lines)
        if (match := _HEADING.match(line))
    ]
    errors: list[str] = []
    seen_unreleased = False
    seen_earlier = False
    seen_versions: set[tuple[int, int, int]] = set()
    previous: tuple[int, int, int] | None = None
    for position, (index, heading) in enumerate(headings):
        end = headings[position + 1][0] if position + 1 < len(headings) else len(lines)
        if heading == "Earlier releases":
            if seen_earlier:
                errors.append(f"line {index + 1}: duplicate {_EARLIER} heading")
            seen_earlier = True
            if not seen_versions:
                errors.append(f"line {index + 1}: {_EARLIER} must follow a version heading")
            continue
        if heading == "Unreleased":
            if seen_unreleased:
                errors.append(f"line {index + 1}: duplicate {_UNRELEASED} heading")
            seen_unreleased = True
            if position != 0:
                errors.append(f"line {index + 1}: {_UNRELEASED} must be the first release heading")
            errors.extend(
                f"line {index + 1}: {error}" for error in _unreleased_errors(lines, index + 1, end)
            )
            continue
        match = _VERSION.fullmatch(lines[index])
        if match is None:
            errors.append(
                f"line {index + 1}: invalid release heading {lines[index]!r}; "
                "use '## Unreleased' or '## vX.Y.Z — YYYY-MM-DD'"
            )
            continue
        if seen_earlier:
            errors.append(f"line {index + 1}: version heading cannot follow {_EARLIER}")
        version = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
        try:
            date.fromisoformat(match.group(4))
        except ValueError:
            errors.append(f"line {index + 1}: invalid release date {match.group(4)!r}")
        if version in seen_versions:
            errors.append(
                f"line {index + 1}: duplicate release version v{match.group(1)}."
                f"{match.group(2)}.{match.group(3)}"
            )
        seen_versions.add(version)
        if previous is not None and version >= previous:
            errors.append(
                f"line {index + 1}: release v{match.group(1)}.{match.group(2)}."
                f"{match.group(3)} is out of order"
            )
        previous = version
    return errors


def stamp_text(text: str, version: str, today: str) -> str:
    """Stamp the first ``## Unreleased`` heading and return the new text."""
    if _PLAIN_VERSION.fullmatch(version) is None:
        raise ValueError(f"not a version: {version}")
    try:
        date.fromisoformat(today)
    except ValueError as exc:
        raise ValueError(f"not a date: {today}") from exc
    lines = text.splitlines(keepends=True)
    headings = [index for index, line in enumerate(lines) if _HEADING.match(line)]
    unreleased = [index for index in headings if lines[index].strip() == _UNRELEASED]
    if not unreleased:
        raise ValueError(f"CHANGELOG.md has no {_UNRELEASED} section")
    if len(unreleased) > 1:
        raise ValueError(f"CHANGELOG.md has more than one {_UNRELEASED} section")
    index = unreleased[0]
    if headings[0] != index:
        raise ValueError(f"{_UNRELEASED} must be the first release heading")
    end = headings[1] if len(headings) > 1 else len(lines)
    errors = _unreleased_errors(lines, index + 1, end)
    if errors:
        raise ValueError(errors[0])
    ending = "\r\n" if lines[index].endswith("\r\n") else "\n"
    lines[index] = f"## v{version} — {today}{ending}"
    stamped = "".join(lines)
    errors = check_text(stamped)
    if errors:
        raise ValueError(errors[0])
    return stamped


def stamp_file(version: str, today: str | None = None) -> str:
    """Stamp the root changelog and its packaged copy; return the date used."""
    day = today or date.today().isoformat()
    stamped = stamp_text(SOURCE.read_text(encoding="utf-8"), version, day)
    SOURCE.write_text(stamped, encoding="utf-8", newline="")
    PACKAGED.parent.mkdir(parents=True, exist_ok=True)
    PACKAGED.write_text(stamped, encoding="utf-8", newline="")
    return day


def main(argv: list[str] | None = None) -> int:
    """Run the gate or stamp the next release heading."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stamp", metavar="VERSION", help="stamp ## Unreleased as VERSION")
    args = parser.parse_args(argv)
    if args.stamp is not None:
        try:
            day = stamp_file(args.stamp)
        except (OSError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(f"stamped CHANGELOG.md as v{args.stamp} — {day}")
        return 0
    try:
        source = SOURCE.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"error: cannot read {_label(SOURCE)}: {exc}", file=sys.stderr)
        return 1
    errors = check_text(source)
    try:
        packaged = PACKAGED.read_bytes()
    except OSError as exc:
        print(f"error: cannot read {_label(PACKAGED)}: {exc}", file=sys.stderr)
        return 1
    if packaged != SOURCE.read_bytes():
        errors.append(
            f"{_label(PACKAGED)} is stale; run: cp CHANGELOG.md src/lazyplan/data/CHANGELOG.md"
        )
    if errors:
        print("changelog check failed:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print("changelog ok: headings dated and packaged copy matches")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
