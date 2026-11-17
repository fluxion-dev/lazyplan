"""The inventory tool counts modules, groups matrices, and checks the keep matrix."""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path
from typing import Any

from tests.support.paths import ROOT


def _load() -> Any:
    spec = importlib.util.spec_from_file_location(
        "test_inventory", ROOT / "tools/test_inventory.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class InventoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tool = _load()

    def test_name_key_is_the_subject_words(self) -> None:
        self.assertEqual(self.tool.name_key("test_task_row_hides_claim"), ("task",))
        self.assertEqual(self.tool.name_key("test_plan"), ("plan",))

    def test_matrices_group_only_same_subject_groups(self) -> None:
        info = self.tool.ModuleInfo(module="tests.x.test_a", area="x")
        info.methods = ["test_row_a", "test_row_b", "test_other_a", "test_row_c"]
        inventory = self.tool.Inventory(
            modules={info.module: info},
            areas={"x": [info.module]},
            method_ids=[],
            seconds={},
        )
        groups = self.tool.matrices(inventory, minimum=3)
        self.assertEqual(
            groups, [("tests.x.test_a", ("row",), ["test_row_a", "test_row_b", "test_row_c"])]
        )

    def test_a_missing_keep_test_is_an_error(self) -> None:
        matrix = (("store rows", ("tests.store.test_store.StoreTest.test_create",)),)
        errors = self.tool.keep_matrix_errors(
            ["tests.store.test_store.StoreTest.test_create"], matrix
        )
        self.assertEqual(errors, [])
        self.assertEqual(len(self.tool.keep_matrix_errors([], matrix)), 1)

    def test_scan_module_counts_fixture_hooks_and_markers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "test_a.py"
            path.write_text(
                "class A:\n    def setUp(self):\n        self.s = Store('x')\n",
                encoding="utf-8",
            )
            setups, markers, helpers = self.tool.scan_module(path)
        self.assertEqual((setups, markers, helpers), (1, 1, []))

    def test_every_keep_matrix_test_exists(self) -> None:
        inventory = self.tool.build_inventory()
        self.assertEqual(self.tool.keep_matrix_errors(inventory.method_ids), [])

    def test_duplicate_map_names_a_live_canonical_table(self) -> None:
        inventory = self.tool.build_inventory()
        self.assertEqual(self.tool.duplicate_map_errors(inventory.method_ids), [])
        for canonical, absorbed in self.tool.DUPLICATE_MAP.items():
            self.assertNotIn(canonical, absorbed)

    def test_render_is_deterministic(self) -> None:
        inventory = self.tool.build_inventory()
        self.assertEqual(self.tool.render(inventory), self.tool.render(inventory))
        self.assertIn("test inventory", self.tool.render(inventory))


if __name__ == "__main__":
    unittest.main()
