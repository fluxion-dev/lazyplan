"""No two Store map methods repeat the same row-iteration logic.

Every ``*_map`` method is a bulk read that groups rows by a key. When two of
them contain the same grouping loop, the grouping is written once per method
instead of once in the base. ``BASELINE_DUPLICATES`` records today's groups so
the cleanup can shrink it to zero without a red commit in between.

Bodies are compared after erasing names, attribute names, constants, and
annotations, so two methods that differ only in row type or column name still
count as one shape. A method that only delegates to a shared helper carries no
row iteration of its own, so it is not compared: the helper is the one
implementation. Every ``*_map`` in the package is an implementation now that
the declaration mirrors are gone.
"""

from __future__ import annotations

import ast
import hashlib
import tempfile
import unittest
from pathlib import Path

STORE = Path(__file__).resolve().parents[2] / "src" / "lazyplan" / "store"

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


def _bodies(root: Path = STORE) -> list[tuple[str, str, bool]]:
    """One ``(method name, body digest, own logic)`` row per public map read."""
    found: list[tuple[str, str, bool]] = []
    for path in sorted(root.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            for item in node.body:
                if not isinstance(item, ast.FunctionDef) or not item.name.endswith("_map"):
                    continue
                if item.name.startswith("_"):
                    continue
                body = [statement for statement in item.body if not _is_docstring(statement)]
                own_logic = not _delegates(body)
                shape = tuple(_Shape().visit(statement) for statement in body)
                dump = ast.dump(
                    ast.Module(body=list(shape), type_ignores=[]), annotate_fields=False
                )
                digest = hashlib.sha1(dump.encode()).hexdigest()
                found.append((item.name, digest, own_logic))
    return found


#: Helpers that own the read; a one-line call to one of them is not a duplicate.
SHARED_READERS = frozenset({"_grouped", "_indexed", "_text_map"})


def _delegates(body: list[ast.stmt]) -> bool:
    """True when the whole body is one return of a shared reader call."""
    if len(body) != 1 or not isinstance(body[0], ast.Return):
        return False
    value = body[0].value
    return (
        isinstance(value, ast.Call)
        and isinstance(value.func, ast.Attribute)
        and value.func.attr in SHARED_READERS
    )


def duplicate_groups(root: Path = STORE) -> list[tuple[str, ...]]:
    """Methods with their own logic and identical bodies, one sorted group each."""
    by_body: dict[str, list[str]] = {}
    for name, digest, own_logic in _bodies(root):
        if own_logic:
            by_body.setdefault(digest, []).append(name)
    return sorted(tuple(sorted(names)) for names in by_body.values() if len(names) > 1)


def map_methods(root: Path = STORE) -> list[str]:
    """Every public Store map method name, in file order."""
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

    def test_each_map_method_is_defined_once(self) -> None:
        names = map_methods()
        self.assertEqual(sorted(names), sorted(set(names)), "a map method is defined twice")

    def test_gate_detects_a_seeded_duplicate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seeded_pair(root)
            self.assertEqual(duplicate_groups(root), [("left_map", "right_map")])


if __name__ == "__main__":
    unittest.main()
