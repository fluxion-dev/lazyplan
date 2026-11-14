"""The Store contract declares each method once.

The duplicate baseline is recorded here so the cleanup can ratchet it to zero
without a red commit in between. Every duplicate carries the port files that
declare it, so the cleanup slices know exactly which declaration to move.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

PORTS = Path(__file__).resolve().parents[2] / "src" / "lazyplan" / "core" / "ports"

#: Method name to the port modules that declare it more than once today.
BASELINE_DUPLICATES: dict[str, tuple[str, ...]] = {}

#: Declarations beyond the first for each duplicated name.
BASELINE_EXTRA = 0


def protocol_methods() -> dict[str, tuple[str, ...]]:
    """Method name to the sorted port modules whose protocols declare it."""
    found: dict[str, list[str]] = {}
    for path in sorted(PORTS.glob("*.py")):
        if path.name == "__init__.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            if not any("Protocol" in ast.unparse(base) for base in node.bases):
                continue
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    found.setdefault(item.name, []).append(path.stem)
    return {name: tuple(sorted(set(files))) for name, files in found.items()}


def duplicates() -> dict[str, tuple[str, ...]]:
    """Method names declared by more than one protocol, with their files."""
    return {name: files for name, files in protocol_methods().items() if len(files) > 1}


def extra_declarations() -> int:
    """Declarations beyond the first for each duplicated name."""
    return sum(len(files) - 1 for files in duplicates().values())


class StoreContractBaselineTest(unittest.TestCase):
    def test_duplicate_baseline_is_recorded(self) -> None:
        self.assertEqual(duplicates(), BASELINE_DUPLICATES)

    def test_extra_declaration_baseline_is_recorded(self) -> None:
        self.assertEqual(extra_declarations(), BASELINE_EXTRA)


if __name__ == "__main__":
    unittest.main()
