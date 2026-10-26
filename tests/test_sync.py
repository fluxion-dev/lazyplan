"""Plan UIDs and plan-level sync."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from lazyplan import services, sync  # noqa: E402
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


class TestSync(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        source = Store(os.path.join(self.tmp.name, "source.db"))
        plan = source.add_plan("P", "what", goal="why", actor="fixture")
        milestone = source.add_milestone(plan.id, "M", actor="fixture")
        source.add_task(milestone.id, "T", "desc", actor="fixture")
        self.data = services.export_all(source)
        self.target = Store(os.path.join(self.tmp.name, "target.db"))

    def tearDown(self):
        self.tmp.cleanup()

    def test_add_then_skip(self):
        first = sync.sync(self.target, self.data, actor="fixture")
        self.assertEqual(len(first["added"]), 1)
        self.assertEqual(len(first["skipped"]), 0)
        second = sync.sync(self.target, self.data, actor="fixture")
        self.assertEqual(second["added"], [])
        self.assertEqual(len(second["skipped"]), 1)
        self.assertEqual(len(self.target.list_plans()), 1)

    def test_conflict_does_not_write(self):
        sync.sync(self.target, self.data, actor="fixture")
        changed = json.loads(json.dumps(self.data))
        changed["plans"][0]["plan"]["name"] = "Different"
        report = sync.sync(self.target, changed, actor="fixture")
        self.assertEqual(len(report["conflicts"]), 1)
        self.assertIn("name", report["conflicts"][0]["differences"])
        self.assertEqual(self.target.get_plan(1).name, "P")

    def test_dry_run_writes_nothing(self):
        report = sync.sync(self.target, self.data, actor="fixture", dry_run=True)
        self.assertTrue(report["dry_run"])
        self.assertEqual(len(report["added"]), 1)
        self.assertEqual(self.target.list_plans(), [])

    def test_duplicate_uid_in_file_is_a_conflict(self):
        duplicate = json.loads(json.dumps(self.data))
        duplicate["plans"].append(duplicate["plans"][0])
        report = sync.sync(self.target, duplicate, actor="fixture")
        self.assertEqual(len(report["conflicts"]), 1)
        self.assertIn("duplicate-uid", report["conflicts"][0]["differences"])


if __name__ == "__main__":
    unittest.main()
