"""Transfer use cases over the transfer port."""

from __future__ import annotations

import os
import tempfile
import unittest

from lazyplan import services
from lazyplan.store import Store


class TestTransferService(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(os.path.join(self.tmp.name, "transfer.db"))
        plan = self.store.add_plan("P", "what", goal="why", actor="fixture")
        self.store.add_criteria("plan", plan.id, "works", actor="fixture")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_export_import_round_trip(self) -> None:
        dump = services.export_all(self.store)
        self.assertEqual(dump["lazyplan"], 1)
        with tempfile.TemporaryDirectory() as other:
            target = Store(os.path.join(other, "target.db"))
            counts = services.import_all(target, dump, actor="fixture")
            self.assertEqual(counts["plans"], 1)
            self.assertEqual(target.list_plans()[0].name, "P")

    def test_share_payload_is_redacted(self) -> None:
        plan_id = self.store.list_plans()[0].id
        self.assertIn("plan", services.export_plan(self.store, plan_id))


if __name__ == "__main__":
    unittest.main()
