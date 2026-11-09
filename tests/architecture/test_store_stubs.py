"""Every StoreStubs declaration must have a real implementation."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "lazyplan"
STUBS = SRC / "store" / "stubs.py"


def stub_methods() -> set[str]:
    """Method names declared on the StoreStubs base."""
    tree = ast.parse(STUBS.read_text(encoding="utf-8"))
    cls = next(
        node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "StoreStubs"
    )
    return {
        node.name for node in cls.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def implemented_methods() -> set[str]:
    """Method names defined outside the stub base."""
    found: set[str] = set()
    for path in SRC.rglob("*.py"):
        if path == STUBS or "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                found.add(node.name)
    return found


class StoreStubAuditTest(unittest.TestCase):
    def test_every_stub_has_an_implementation(self) -> None:
        missing = sorted(stub_methods() - implemented_methods())
        self.assertEqual(missing, [], f"remove dead StoreStubs declarations: {missing}")
