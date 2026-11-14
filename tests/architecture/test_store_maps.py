"""No two Store map methods repeat the same row-iteration logic.

Every ``*_map`` method is a bulk read that groups rows by a key. When two of
them contain the same grouping loop, the grouping is written once per method
instead of once in the base. ``BASELINE_DUPLICATES`` records today's groups so
the cleanup can shrink it to zero without a red commit in between.

Bodies are compared after erasing names, attribute names, constants, and
annotations, so two methods that differ only in row type or column name still
count as one shape. A method that only delegates to a shared helper carries no
row iteration of its own, so it is not compared: the helper is the one
implementation. The declaration mirrors in ``store/stubs*.py`` are signatures,
not implementations, and are skipped.
"""

from __future__ import annotations

import ast
import hashlib
import tempfile
import unittest
from pathlib import Path

STORE = Path(__file__).resolve().parents[2] / "src" / "lazyplan" / "store"

#: Files that only mirror declarations, so they carry no grouping logic.
MIRRORS = frozenset({"stubs.py", "stubs_links.py"})

#: Normalized-body groups to collapse, sorted by method name.
BASELINE_DUPLICATES: tuple[tuple[str, ...], ...] = ()


class _Shape(ast.NodeTransformer):
    """Erase the names a body uses so only its statements remain."""

    def visit_Name(self, node: ast.Name) -> ast.AST:
        return ast.copy_location(ast.Name(id="_", ctx=node.ctx), node)

    def visit_Attribute(self, node: ast.Attribute) -> ast.AST:
        self.generic_visit(node)
        node.attr = "_"
        return node

    def visit_Constant(self, node: ast.Constant) -> ast.AST:
        return ast.copy_location(ast.Constant(value=None), node)

    def visit_arg(self, node: ast.arg) -> ast.AST:
        return ast.copy_location(ast.arg(arg="_", annotation=None), node)


def _is_docstring(statement: ast.stmt) -> bool:
    """True for a bare string expression, which documents instead of shaping."""
    return (
        isinstance(statement, ast.Expr)
        and isinstance(statement.value, ast.Constant)
        and isinstance(statement.value.value, str)
    )


def _bodies(root: Path) -> list[tuple[str, str, bool]]:
    """One ``(method name, body digest, iterates)`` row per Store map method."""
    found: list[tuple[str, str, bool]] = []
    for path in sorted(root.glob("*.py")):
        if path.name in MIRRORS:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            for item in node.body:
                if not isinstance(item, ast.FunctionDef) or not item.name.endswith("_map"):
                    continue
                body = [statement for statement in item.body if not _is_docstring(statement)]
                shape = tuple(_Shape().visit(statement) for statement in body)
                dump = ast.dump(
                    ast.Module(body=list(shape), type_ignores=[]), annotate_fields=False
                )
                found.append((item.name, hashlib.sha1(dump.encode()).hexdigest(), _iterates(body)))
    return found


def _iterates(body: list[ast.stmt]) -> bool:
    """True when a body loops over rows itself instead of delegating the read."""
    return any(
        isinstance(node, (ast.For, ast.AsyncFor, ast.While, ast.comprehension))
        for statement in body
        for node in ast.walk(statement)
    )


def duplicate_groups(root: Path = STORE) -> list[tuple[str, ...]]:
    """Iterating methods with identical normalized bodies, one sorted group each."""
    by_body: dict[str, list[str]] = {}
    for name, digest, iterates in _bodies(root):
        if iterates:
            by_body.setdefault(digest, []).append(name)
    return sorted(tuple(sorted(names)) for names in by_body.values() if len(names) > 1)


def map_methods(root: Path = STORE) -> list[str]:
    """Every Store map method name, in file order."""
    return [name for name, _, _ in _bodies(root)]


def _seeded_pair(root: Path) -> None:
    """Write two map reads that differ in names but not in shape."""
    left = (
        "class Left:\n"
        "    def left_map(self):\n"
        '        """Left rows."""\n'
        "        out = {}\n"
        "        for row in self._rows():\n"
        "            out.setdefault(row.kind, []).append(row)\n"
        "        return out\n"
    )
    right = (
        "class Right:\n"
        "    def right_map(self):\n"
        "        found = {}\n"
        "        for item in self._rows():\n"
        "            found.setdefault(item.parent, []).append(item)\n"
        "        return found\n"
    )
    (root / "left.py").write_text(left, encoding="utf-8")
    (root / "right.py").write_text(right, encoding="utf-8")


class StoreMapDuplicateTest(unittest.TestCase):
    def test_duplicate_baseline_is_recorded(self) -> None:
        self.assertEqual(duplicate_groups(), list(BASELINE_DUPLICATES))

    def test_gate_detects_a_seeded_duplicate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seeded_pair(root)
            self.assertEqual(duplicate_groups(root), [("left_map", "right_map")])

    def test_gate_ignores_the_stub_mirror(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seeded_pair(root)
            (root / "stubs.py").write_text(
                (root / "left.py").read_text(encoding="utf-8"), encoding="utf-8"
            )
            self.assertEqual(duplicate_groups(root), [("left_map", "right_map")])


if __name__ == "__main__":
    unittest.main()
