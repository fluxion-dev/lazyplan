"""Criterion-task relations: many-to-many, cascade, and export/import."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from lazyplan import services  # noqa: E402
from lazyplan.store import Store  # noqa: E402


class TestCriterionLinks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "links.db")
        self.store = Store(self.db)
        plan = self.store.add_plan("P", actor="fixture")
        milestone = self.store.add_milestone(plan.id, "M", actor="fixture")
        self.task = self.store.add_task(milestone.id, "T", actor="fixture")
        self.criterion = self.store.add_criteria("plan", plan.id, "Works", actor="fixture")
        self.task_criterion = self.store.add_criteria(
            "task", self.task.id, "Tested", actor="fixture"
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_relate_is_many_to_many(self):
        second = self.store.add_task(1, "T2", actor="fixture")
        self.assertTrue(self.store.relate_criterion(self.criterion.id, self.task.id))
        self.assertTrue(self.store.relate_criterion(self.criterion.id, second.id))
        self.assertEqual(
            [task.id for task in self.store.criterion_tasks(self.criterion.id)],
            [self.task.id, second.id],
        )
        self.store.relate_criterion(self.task_criterion.id, self.task.id)
        self.assertEqual(
            [crit.id for crit in self.store.task_criteria(self.task.id)],
            [self.criterion.id, self.task_criterion.id],
        )

    def test_duplicate_relation_is_rejected(self):
        self.store.relate_criterion(self.criterion.id, self.task.id)
        with self.assertRaises(ValueError):
            self.store.relate_criterion(self.criterion.id, self.task.id)

    def test_missing_rows_are_rejected(self):
        with self.assertRaises(KeyError):
            self.store.relate_criterion(99, self.task.id)
        with self.assertRaises(KeyError):
            self.store.relate_criterion(self.criterion.id, 99)

    def test_unrelate(self):
        self.store.relate_criterion(self.criterion.id, self.task.id)
        self.assertTrue(self.store.unrelate_criterion(self.criterion.id, self.task.id))
        self.assertEqual(self.store.criterion_tasks(self.criterion.id), [])
        self.assertFalse(self.store.unrelate_criterion(self.criterion.id, self.task.id))

    def test_deleting_either_side_cascades(self):
        self.store.relate_criterion(self.criterion.id, self.task.id)
        self.store.delete("task", self.task.id)
        self.assertEqual(self.store.criterion_tasks(self.criterion.id), [])

        second = self.store.add_task(1, "T2", actor="fixture")
        self.store.relate_criterion(self.criterion.id, second.id)
        self.store.delete_criteria(self.criterion.id)
        self.assertEqual(self.store.task_criteria(second.id), [])

    def test_export_and_import_preserve_relations(self):
        self.store.relate_criterion(self.criterion.id, self.task.id)
        data = services.export_all(self.store)
        self.assertEqual(data["criterion_links"], [{"criterion_id": 1, "task_id": 1}])
        other = Store(os.path.join(self.tmp.name, "other.db"))
        counts = services.import_all(other, data, actor="fixture")
        self.assertEqual(counts["criterion_links"], 1)
        self.assertEqual([task.id for task in other.criterion_tasks(1)], [1])

    def test_all_links_lists_pairs(self):
        self.store.relate_criterion(self.criterion.id, self.task.id)
        self.assertEqual(
            self.store.all_criterion_links(),
            [{"criterion_id": self.criterion.id, "task_id": self.task.id}],
        )


if __name__ == "__main__":
    unittest.main()
