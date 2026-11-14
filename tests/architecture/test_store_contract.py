"""The Store contract: one declaration per method, and a real implementation.

Ports declare the surface once. The assembled Store provides every declared
method from a concrete mixin, so a signature change is one declaration and one
implementation, never a third mirror to keep in step.
"""

from __future__ import annotations

import ast
import tempfile
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "lazyplan"
PORTS = SRC / "core" / "ports"
STORE = SRC / "store"

#: Declarations that only exist under ``TYPE_CHECKING`` in the store base.
INTERNAL_CONTRACT = STORE / "base.py"


def _is_protocol(node: ast.ClassDef) -> bool:
    """True when a class body declares a Protocol."""
    return any("Protocol" in ast.unparse(base) for base in node.bases)


def protocol_declarations(ports: Path) -> dict[str, list[str]]:
    """Method name to the port modules that declare it."""
    found: dict[str, list[str]] = {}
    for path in sorted(ports.glob("*.py")):
        if path.name == "__init__.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef) or not _is_protocol(node):
                continue
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    found.setdefault(item.name, []).append(path.stem)
    return {name: sorted(set(files)) for name, files in found.items()}


def duplicates(declarations: dict[str, list[str]]) -> dict[str, list[str]]:
    """Declarations made by more than one protocol, with their modules."""
    return {name: files for name, files in declarations.items() if len(files) > 1}


def internal_declarations(base: Path) -> set[str]:
    """Private cross-mixin helpers declared by the assembled Store contract."""
    tree = ast.parse(base.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "_StoreContract":
            return {
                item.name
                for item in node.body
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
    return set()


def store_implementations(store: Path) -> set[str]:
    """Methods a concrete Store class defines, excluding contract declarations."""
    found: set[str] = set()
    for path in sorted(store.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef) or node.name.startswith("_"):
                continue
            if _is_protocol(node):
                continue
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    found.add(item.name)
    return found


class StoreContractTest(unittest.TestCase):
    def test_each_method_is_declared_once(self) -> None:
        self.assertEqual(duplicates(protocol_declarations(PORTS)), {})

    def test_every_contract_method_is_implemented(self) -> None:
        declared = set(protocol_declarations(PORTS)) | internal_declarations(INTERNAL_CONTRACT)
        missing = sorted(declared - store_implementations(STORE))
        self.assertEqual(missing, [], f"implement the contract methods: {missing}")

    def test_gate_detects_a_seeded_duplicate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ports = Path(tmp) / "ports"
            ports.mkdir()
            (ports / "left.py").write_text(
                "from typing import Protocol\n\n"
                "class Left(Protocol):\n"
                "    def ping(self) -> None: ...\n",
                encoding="utf-8",
            )
            (ports / "right.py").write_text(
                "from typing import Protocol\n\n"
                "class Right(Protocol):\n"
                "    def ping(self) -> None: ...\n",
                encoding="utf-8",
            )
            self.assertEqual(duplicates(protocol_declarations(ports)), {"ping": ["left", "right"]})


if __name__ == "__main__":
    unittest.main()
