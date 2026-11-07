#!/usr/bin/env python3
"""Documentation gate: one human doc set and no broken relative links.

Usage:
  python3 tools/check-docs.py

Stdlib only. Fails when Markdown outside the allowlist appears, when a retained
human doc links to a missing relative path, or when ``AGENTS.md`` loses the
documentation policy sentence.

``LEGACY_DOCS`` is transitional: milestone 446 and the site slice delete those
docs and must clear the set. An entry that no longer exists is an error, so the
allowance cannot linger.
"""

from __future__ import annotations

import os
import re
import sys
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent

HUMAN_DOCS = ("README.md", "CONTRIBUTING.md", "docs/usage.md")
ALLOWED = frozenset({*HUMAN_DOCS, "AGENTS.md", "CHANGELOG.md"})
RETIRED_DOCS = frozenset(
    {
        "docs/architecture.md",
        "docs/design-system.md",
        "docs/downloads.md",
        "docs/performance.md",
        "docs/releasing.md",
        "docs/setup.md",
    }
)
LEGACY_DOCS = frozenset({"docs/product/roadmap.md"})
POLICY_FILE = "AGENTS.md"
POLICY_MARKER = "Do not restate source"
SKIP_DIRS = frozenset(
    {
        ".git",
        ".venv",
        ".agents",
        ".lazyplan",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "__pycache__",
        "build",
        "dist",
        "node_modules",
        "tests",
    }
)
SKIP_PREFIXES = ("src/lazyplan/data/",)

LINK = re.compile(r"!?\[[^\]]*\]\(\s*([^)\s]+)(?:\s+\"[^\"]*\")?\s*\)")
INLINE_CODE = re.compile(r"`[^`]*`")
EXTERNAL_PREFIXES = ("http://", "https://", "//", "mailto:", "data:")


def markdown_files(root: Path) -> Iterator[str]:
    """Yield repo-relative Markdown paths outside the skip set."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(name for name in dirnames if name not in SKIP_DIRS)
        for filename in sorted(filenames):
            if not filename.endswith(".md"):
                continue
            relative = (Path(dirpath) / filename).relative_to(root).as_posix()
            if relative.startswith(SKIP_PREFIXES):
                continue
            yield relative


def prose_links(text: str) -> Iterator[tuple[int, str]]:
    """Yield ``(line, target)`` for links outside fences and inline code."""
    fenced = False
    for number, line in enumerate(text.splitlines(), 1):
        stripped = line.lstrip()
        if stripped.startswith(("```", "~~~")):
            fenced = not fenced
            continue
        if fenced:
            continue
        for match in LINK.finditer(INLINE_CODE.sub("", line)):
            yield number, match.group(1)


def is_external(target: str) -> bool:
    """True when *target* leaves the repo or stays on the page."""
    return target.startswith(EXTERNAL_PREFIXES) or target.startswith("#")


def resolve(root: Path, source: str, target: str) -> Path:
    """Resolve a Markdown target relative to its source file."""
    parsed = urlsplit(target)
    path = parsed.path
    base = root if path.startswith("/") else (root / source).parent
    return (base / path.lstrip("/")).resolve()


def check_links(root: Path) -> list[str]:
    """Return errors for missing relative links in the retained human docs."""
    errors: list[str] = []
    for name in HUMAN_DOCS:
        path = root / name
        if not path.is_file():
            errors.append(f"missing human doc: {name}")
            continue
        for line, target in prose_links(path.read_text(encoding="utf-8")):
            if is_external(target):
                continue
            resolved = resolve(root, name, target)
            if not resolved.exists():
                errors.append(f"{name}:{line}: broken relative link: {target}")
    return errors


def check_allowlist(root: Path) -> list[str]:
    """Return errors for unapproved, missing, or stale Markdown paths."""
    present = set(markdown_files(root))
    errors = [f"unapproved Markdown: {name}" for name in sorted(present - ALLOWED - LEGACY_DOCS)]
    errors.extend(f"missing human doc: {name}" for name in HUMAN_DOCS if name not in present)
    errors.extend(
        f"legacy doc is gone; remove it from LEGACY_DOCS: {name}"
        for name in sorted(LEGACY_DOCS - present)
    )
    return errors


def check_policy(root: Path) -> list[str]:
    """Return errors when AGENTS.md is missing or lacks the policy sentence."""
    path = root / POLICY_FILE
    if not path.is_file():
        return [f"missing {POLICY_FILE}"]
    if POLICY_MARKER not in path.read_text(encoding="utf-8"):
        return [f"{POLICY_FILE} must state the documentation policy: {POLICY_MARKER!r}"]
    return []


def check(root: Path) -> list[str]:
    """Return every documentation-gate failure under *root*."""
    return [*check_allowlist(root), *check_links(root), *check_policy(root)]


def main() -> int:
    """Run the gate and print a readable verdict."""
    errors = check(ROOT)
    if errors:
        print("docs check failed:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print("docs ok: README, CONTRIBUTING, usage, CHANGELOG, AGENTS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
