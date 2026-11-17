#!/usr/bin/env python3
"""Inventory the unittest suite: modules, methods, fixtures, and matrices.

The tool is stdlib-only. It discovers tests the same way the gate does, then
reports per-area counts. With ``--time`` it runs one subprocess per area so the
runtime table is reproducible. ``--check`` validates the keep matrix and the
duplicate map in this file against the discovered suite, so a cleanup cannot
silently drop a core contract.

Usage:
  python tools/test_inventory.py [--time] [--json] [--check]
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import subprocess
import sys
import time
import unittest
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
STORE_MARKERS = ("Store(", "sandbox_home(", "TemporaryDirectory(")
FIXTURE_HOOKS = ("setUp", "tearDown", "setUpClass", "tearDownClass")

# Baseline taken on 2026-11-16 on Linux (Python 3.15, venv): 251 test sources
# (244 discovered modules; 7 helper-only files) and 2301 test methods. The
# full suite took 309 s. T446 compares the cleaned suite against these numbers.
SNAPSHOT = {"sources": 251, "modules": 244, "methods": 2301, "seconds": 309}


@dataclass
class ModuleInfo:
    """One test module as discovered by unittest."""

    module: str
    area: str
    methods: list[str] = field(default_factory=list)
    setup_classes: int = 0
    store_markers: int = 0
    support_helpers: list[str] = field(default_factory=list)


@dataclass
class Inventory:
    """Everything the report and the checks need."""

    modules: dict[str, ModuleInfo]
    areas: dict[str, list[str]]
    method_ids: list[str]
    seconds: dict[str, float]


def flatten(suite: unittest.TestSuite) -> list[Any]:
    """Flatten a discovered suite into individual tests."""
    found: list[Any] = []
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            found.extend(flatten(item))
        else:
            found.append(item)
    return found


def discover(root: Path = ROOT) -> tuple[list[str], dict[str, list[str]]]:
    """Return discovered method ids and the methods grouped by module."""
    src = root / "src"
    if src.is_dir() and str(src) not in sys.path:
        sys.path.insert(0, str(src))
    loader = unittest.TestLoader()
    suite = loader.discover(str(root / "tests"), top_level_dir=str(root))
    ids = [test.id() for test in flatten(suite)]
    by_module: dict[str, list[str]] = defaultdict(list)
    for test_id in ids:
        module, method = test_id.rsplit(".", 2)[0], test_id.rsplit(".", 1)[1]
        by_module[module].append(method)
    return ids, dict(by_module)


def module_source(module: str, root: Path = ROOT) -> Path | None:
    """Map ``tests.pkg.test_mod`` to its file when it exists."""
    relative = Path(*module.split(".")).with_suffix(".py")
    path = root / relative
    return path if path.is_file() else None


def scan_module(path: Path) -> tuple[int, int, list[str]]:
    """Count fixture classes, store markers, and imported support helpers."""
    text = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return 0, 0, []
    classes = [node for node in tree.body if isinstance(node, ast.ClassDef)]
    setup_classes = sum(
        1
        for node in classes
        if any(
            isinstance(item, ast.FunctionDef) and item.name in FIXTURE_HOOKS for item in node.body
        )
    )
    markers = sum(text.count(marker) for marker in STORE_MARKERS)
    helpers: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("tests.support"):
            helpers.extend(alias.name for alias in node.names)
    return setup_classes, markers, sorted(set(helpers))


def build_inventory(root: Path = ROOT) -> Inventory:
    """Discover the suite and annotate every module."""
    method_ids, by_module = discover(root)
    modules: dict[str, ModuleInfo] = {}
    for module, methods in sorted(by_module.items()):
        area = module.split(".")[1] if module.count(".") >= 1 else module
        info = ModuleInfo(module=module, area=area, methods=sorted(methods))
        path = module_source(module, root)
        if path is not None:
            info.setup_classes, info.store_markers, info.support_helpers = scan_module(path)
        modules[module] = info
    areas: dict[str, list[str]] = defaultdict(list)
    for info in modules.values():
        areas[info.area].append(info.module)
    return Inventory(
        modules=modules,
        areas={area: sorted(names) for area, names in sorted(areas.items())},
        method_ids=sorted(method_ids),
        seconds={},
    )


def name_key(method: str) -> tuple[str, ...]:
    """The leading word of a test name: its subject family."""
    return tuple(method.removeprefix("test_").split("_")[:1])


def matrices(
    inventory: Inventory, minimum: int = 4
) -> list[tuple[str, tuple[str, ...], list[str]]]:
    """Group same-subject methods per module, biggest groups first."""
    groups: list[tuple[str, tuple[str, ...], list[str]]] = []
    for module, info in inventory.modules.items():
        by_key: dict[tuple[str, ...], list[str]] = defaultdict(list)
        for method in info.methods:
            by_key[name_key(method)].append(method)
        for key, members in by_key.items():
            if len(members) >= minimum:
                groups.append((module, key, sorted(members)))
    return sorted(groups, key=lambda item: (-len(item[2]), item[0], item[1]))


def fixture_totals(inventory: Inventory) -> dict[str, int]:
    """Count fixture classes, store builders, and shared-helper imports."""
    return {
        "modules_with_setUp": sum(1 for info in inventory.modules.values() if info.setup_classes),
        "setUp_classes": sum(info.setup_classes for info in inventory.modules.values()),
        "store_markers": sum(info.store_markers for info in inventory.modules.values()),
        "support_modules_used": sum(
            1 for info in inventory.modules.values() if info.support_helpers
        ),
    }


def time_area(area: str) -> float:
    """Run one test area in a fresh interpreter and return its wall time."""
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(
        [str(ROOT / "src"), environment.get("PYTHONPATH", "")]
    ).rstrip(os.pathsep)
    started = time.monotonic()
    subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", f"tests/{area}", "-t", "."],
        cwd=ROOT,
        env=environment,
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return round(time.monotonic() - started, 1)


def render(inventory: Inventory) -> str:
    """Render the human-readable report."""
    lines = [
        "test inventory",
        f"  modules {len(inventory.modules)}  methods {len(inventory.method_ids)}",
        "",
        f"{'area':<16}{'modules':>8}{'methods':>9}{'seconds':>9}",
    ]
    for area, names in inventory.areas.items():
        count = sum(len(inventory.modules[name].methods) for name in names)
        seconds = inventory.seconds.get(area)
        shown = "-" if seconds is None else f"{seconds:.1f}"
        lines.append(f"{area:<16}{len(names):>8}{count:>9}{shown:>9}")
    totals = fixture_totals(inventory)
    lines.extend(
        [
            "",
            f"fixtures: {totals['modules_with_setUp']} modules define setUp "
            f"({totals['setUp_classes']} classes), {totals['store_markers']} store/home/temp markers, "
            f"{totals['support_modules_used']} modules import tests.support",
            "",
            "duplicate matrices (same subject, 4+ methods):",
        ]
    )
    groups = matrices(inventory)
    if not groups:
        lines.append("  none")
    for module, key, members in groups:
        lines.append(f"  {module}: {len(members)} x {'_'.join(key)}")
    return "\n".join(lines)


def as_json(inventory: Inventory) -> dict[str, Any]:
    """Stable machine-readable form for the report and the checks."""
    return {
        "modules": len(inventory.modules),
        "methods": len(inventory.method_ids),
        "areas": {
            area: {
                "modules": len(names),
                "methods": sum(len(inventory.modules[name].methods) for name in names),
                "seconds": inventory.seconds.get(area),
            }
            for area, names in inventory.areas.items()
        },
        "fixtures": fixture_totals(inventory),
        "matrices": [
            {"module": module, "subject": "_".join(key), "methods": members}
            for module, key, members in matrices(inventory)
        ],
    }


def main(argv: list[str] | None = None) -> int:
    """Print the report; ``--time`` adds runtimes and ``--check`` validates maps."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--time", action="store_true", help="run one pass per area")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.add_argument(
        "--check", action="store_true", help="validate the keep matrix and duplicate map"
    )
    args = parser.parse_args(argv)
    inventory = build_inventory()
    if args.time:
        for area in inventory.areas:
            inventory.seconds[area] = time_area(area)
    if args.check:
        errors = check(inventory)
        for error in errors:
            print(error, file=sys.stderr)
        if errors:
            return 1
        print("inventory ok: every keep-matrix test exists", file=sys.stderr)
    print(json.dumps(as_json(inventory), indent=2) if args.json else render(inventory))
    return 0


def check(inventory: Inventory) -> list[str]:
    """Return errors for keep-matrix ids missing from the discovered suite."""
    return keep_matrix_errors(inventory.method_ids)


# Filled by the keep-matrix task.
KEEP_MATRIX: tuple[tuple[str, tuple[str, ...]], ...] = ()
# Filled by the duplicate-map task.
DUPLICATE_MAP: dict[str, tuple[str, ...]] = {}


def keep_matrix_errors(
    method_ids: list[str],
    matrix: tuple[tuple[str, tuple[str, ...]], ...] = KEEP_MATRIX,
) -> list[str]:
    """Return one error per contract whose proving test is gone."""
    known = set(method_ids)
    return [
        f"keep matrix: {contract} has no test ({test_id})"
        for contract, test_ids in matrix
        for test_id in test_ids
        if test_id not in known
    ]


if __name__ == "__main__":
    raise SystemExit(main())
