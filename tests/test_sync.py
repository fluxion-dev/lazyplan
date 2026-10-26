"""Plan UIDs and plan-level sync."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from lazyplan import services  # noqa: E402
from lazyplan.store import Store  # noqa: E402


class TestPlanUids(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "uid.db")
        self.store = Store(self.db)
        self.plan = self.store.add_plan("P", "what", goal="why", actor="fixture")

    def tearDown(self):
        self.tmp.cleanup()

    def test_uid_is_stable_and_unique(self):
        uid = self.store.plan_uid(self.plan.id)
        self.assertTrue(uid)
        other = self.store.add_plan("Q", actor="fixture")
        self.assertNotEqual(uid, self.store.plan_uid(other.id))
        self.assertEqual(self.store.get_plan_by_uid(uid).id, self.plan.id)

    def test_export_import_preserves_uid(self):
        uid = self.store.plan_uid(self.plan.id)
        data = services.export_all(self.store)
        self.assertEqual(data["plans"][0]["plan"]["uid"], uid)
        other = Store(os.path.join(self.tmp.name, "other.db"))
        services.import_all(other, data, actor="fixture")
        self.assertEqual(other.plan_uid(1), uid)

    def test_legacy_dump_without_uid_gets_one(self):
        data = services.export_all(self.store)
        data["plans"][0]["plan"].pop("uid")
        other = Store(os.path.join(self.tmp.name, "legacy.db"))
        services.import_all(other, data, actor="fixture")
        self.assertTrue(other.plan_uid(1))


if __name__ == "__main__":
    unittest.main()
