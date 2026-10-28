"""Guard the internal dependency graph against cycles and layer inversions.

``architecture_baseline.json`` carries the temporary layer exceptions and
per-file budgets. Keep it valid JSON: a comment belongs in this docstring or
the slice that changes the baseline.
"""

from __future__ import annotations

import ast
import json
import unittest
from collections.abc import Iterator
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "lazyplan"
BASELINE = Path(__file__).with_name("architecture_baseline.json")
PACKAGE = "lazyplan"

LEAF = 0
INFRA = 1
STORE = 2
DOMAIN = 3
SERVICES = 4
PRESENTATION = 5
ENTRY = 6

LAYERS: dict[str, int] = {
    "lazyplan": LEAF,
    "kinds": LEAF,
    "models": LEAF,
    "messages": LEAF,
    "textfile": LEAF,
    "porcelain": LEAF,
    "palette": LEAF,
    "help": PRESENTATION,
    "docs_meta": LEAF,
    "repo": INFRA,
    "vcs": INFRA,
    "forge": INFRA,
    "github": INFRA,
    "templates": INFRA,
    "store": STORE,
    "migrate": STORE,
    "audit": DOMAIN,
    "brief": DOMAIN,
    "hooks": DOMAIN,
    "issues": DOMAIN,
    "seed": DOMAIN,
    "share": DOMAIN,
    "source": DOMAIN,
    "stats": DOMAIN,
    "trace": DOMAIN,
    "lint": DOMAIN,
    "services": SERVICES,
    "cli": PRESENTATION,
    "design": PRESENTATION,
    "hook_hosts": PRESENTATION,
    "hook_install": PRESENTATION,
    "mcp": PRESENTATION,
    "render": PRESENTATION,
    "screens": PRESENTATION,
    "setup": PRESENTATION,
    "skills": PRESENTATION,
    "source_screen": PRESENTATION,
    "sync": PRESENTATION,
    "tree_nav": PRESENTATION,
    "tui": PRESENTATION,
    "upgrade": PRESENTATION,
    "__main__": ENTRY,
}


def module_name(path: Path) -> str:
    """Return the import name for *path* under ``src/lazyplan``."""
    parts = list(path.relative_to(SRC).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join((PACKAGE, *parts))


def package_name(path: Path, module: str) -> str:
    """Return the package that relative imports in *path* resolve against."""
    if path.name == "__init__.py":
        return module
    return module.rpartition(".")[0]


def is_type_checking(test: ast.expr) -> bool:
    """Return whether *test* is a ``TYPE_CHECKING`` guard."""
    if isinstance(test, ast.Name):
        return test.id == "TYPE_CHECKING"
    if isinstance(test, ast.Attribute):
        return test.attr == "TYPE_CHECKING"
    return False


def module_imports(node: ast.AST) -> Iterator[ast.Import | ast.ImportFrom]:
    """Yield module-level imports, skipping functions, classes, and type-only blocks."""
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if isinstance(child, ast.If) and is_type_checking(child.test):
            continue
        if isinstance(child, (ast.Import, ast.ImportFrom)):
            yield child
        yield from module_imports(child)


def nearest_module(name: str, known: set[str]) -> str | None:
    """Return *name* or its longest known package prefix."""
    candidate = name
    while candidate:
        if candidate in known:
            return candidate
        candidate = candidate.rpartition(".")[0]
    return None


def resolve(path: Path, module: str, node: ast.Import | ast.ImportFrom) -> set[str]:
    """Return the internal modules imported by *node*."""
    found: set[str] = set()
    if isinstance(node, ast.Import):
        for alias in node.names:
            if alias.name == PACKAGE or alias.name.startswith(f"{PACKAGE}."):
                found.add(alias.name)
        return found

    if node.level:
        base = package_name(path, module)
        for _ in range(node.level - 1):
            base = base.rpartition(".")[0]
        if node.module:
            found.add(f"{base}.{node.module}" if base else node.module)
        else:
            found.update(f"{base}.{alias.name}" for alias in node.names)
    elif node.module and (node.module == PACKAGE or node.module.startswith(f"{PACKAGE}.")):
        found.add(node.module)
    return found


def import_graph() -> dict[str, set[str]]:
    """Return every internal module and the modules it imports."""
    paths = sorted(SRC.rglob("*.py"))
    modules = {module_name(path): path for path in paths}
    known = set(modules)
    graph: dict[str, set[str]] = {name: set() for name in modules}
    for module, path in modules.items():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in module_imports(tree):
            for target in resolve(path, module, node):
                resolved = nearest_module(target, known)
                if resolved is not None and resolved != module:
                    graph[module].add(resolved)
    return graph


def layer_key(module: str) -> str:
    """Return the top-level concern that owns *module*."""
    if module == f"{PACKAGE}.__main__":
        return "__main__"
    parts = module.split(".")
    if len(parts) == 1:
        return PACKAGE
    return parts[1]


def find_cycles(graph: dict[str, set[str]]) -> list[list[str]]:
    """Return each dependency cycle once, as a closed path."""
    state: dict[str, int] = {}
    stack: list[str] = []
    cycles: list[list[str]] = []
    seen: set[frozenset[str]] = set()

    def visit(module: str) -> None:
        state[module] = 1
        stack.append(module)
        for dependency in sorted(graph.get(module, ())):
            if state.get(dependency, 0) == 0:
                visit(dependency)
            elif state.get(dependency) == 1:
                start = stack.index(dependency)
                cycle = stack[start:] + [dependency]
                key = frozenset(cycle)
                if key not in seen:
                    seen.add(key)
                    cycles.append(cycle)
        stack.pop()
        state[module] = 2

    for module in sorted(graph):
        if state.get(module, 0) == 0:
            visit(module)
    return cycles


def layer_violations(
    graph: dict[str, set[str]],
    exceptions: set[tuple[str, str]],
) -> list[str]:
    """Return every edge that points at a higher layer without an exception."""
    violations: list[str] = []
    for source, dependencies in sorted(graph.items()):
        source_key = layer_key(source)
        for target in sorted(dependencies):
            target_key = layer_key(target)
            if (source_key, target_key) in exceptions:
                continue
            if LAYERS[target_key] > LAYERS[source_key]:
                violations.append(f"{source_key} -> {target_key} ({source} -> {target})")
    return violations


class ArchitectureTest(unittest.TestCase):
    """Every internal edge points down a layer and no cycle exists."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.graph = import_graph()
        baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
        cls.exceptions = {tuple(edge) for edge in baseline["layer_exceptions"]}

    def test_no_import_cycles(self) -> None:
        cycles = find_cycles(self.graph)
        self.assertEqual(
            cycles, [], "internal import cycles: " + "; ".join(map(" -> ".join, cycles))
        )

    def test_find_cycles_reports_a_cycle(self) -> None:
        cycles = find_cycles({"a": {"b"}, "b": {"a"}})
        self.assertEqual(cycles, [["a", "b", "a"]])

    def test_every_module_has_a_layer(self) -> None:
        unknown = sorted({layer_key(module) for module in self.graph} - set(LAYERS))
        self.assertEqual(unknown, [], f"classify new modules in LAYERS: {unknown}")

    def test_no_layer_inversion(self) -> None:
        violations = layer_violations(self.graph, self.exceptions)
        self.assertEqual(violations, [], "layer inversions: " + "; ".join(violations))

    def test_layer_inversion_is_reported(self) -> None:
        violations = layer_violations({"lazyplan.store": {"lazyplan.cli"}}, set())
        self.assertEqual(violations, ["store -> cli (lazyplan.store -> lazyplan.cli)"])


if __name__ == "__main__":
    unittest.main()
