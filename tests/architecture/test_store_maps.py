"""No two Store map methods share a function body.

Every ``*_map`` method is a bulk read that groups rows by a key. When two of
them carry the same shape, the grouping is written once per method instead of
once in the base. ``BASELINE_DUPLICATES`` records today's groups so the cleanup
can shrink it to zero without a red commit in between.

Bodies are compared after erasing names, attribute names, constants, and
annotations, so two methods that differ only in row type or column name still
count as one shape. The declaration mirrors in ``store/stubs*.py`` are skipped:
they hold signatures, not implementations.
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
BASELINE_DUPLICATES: tuple[tuple[str, ...], ...] = (
    ("claims_map", "latest_revisions_map"),
    (
        "comments_full_map",
        "criteria_map",
        "forge_links_map",
        "notes_full_map",
        "vcs_links_map",
    ),
    ("comments_map", "notes_map"),
    (
        "evidence_map",
        "milestones_map",
        "plan_worktrees_map",
        "questions_map",
        "refs_map",
        "tasks_map",
    ),
)


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


def _bodies(root: Path) -> list[tuple[str, str]]:
    """One ``(method name, body digest)`` pair per Store map method."""
    found: list[tuple[str, str]] = []
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
                found.append((item.name, hashlib.sha1(dump.encode()).hexdigest()))
    return found


def duplicate_groups(root: Path = STORE) -> list[tuple[str, ...]]:
    """Methods whose normalized bodies are identical, one sorted group each."""
    by_body: dict[str, list[str]] = {}
    for name, digest in _bodies(root):
        by_body.setdefault(digest, []).append(name)
    return sorted(tuple(sorted(names)) for names in by_body.values() if len(names) > 1)


def map_methods(root: Path = STORE) -> list[str]:
    """Every Store map method name, in file order."""
    return [name for name, _ in _bodies(root)]


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
