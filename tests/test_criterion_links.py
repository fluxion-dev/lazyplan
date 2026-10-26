"""Criterion-task relations: many-to-many, cascade, and export/import."""

from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from lazyplan import services  # noqa: E402
from lazyplan.cli import main as lpui_main  # noqa: E402
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


class TestCriterionLinkCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "cli.db")
        store = Store(self.db)
        plan = store.add_plan("P", actor="fixture")
        milestone = store.add_milestone(plan.id, "M", actor="fixture")
        store.add_task(milestone.id, "T", actor="fixture")
        store.add_criteria("plan", plan.id, "Works", actor="fixture")
        self.old_home = os.environ.get("HOME")
        self.old_setup = os.environ.get("LAZYPLAN_NO_SETUP")
        os.environ["HOME"] = self.tmp.name
        os.environ["LAZYPLAN_NO_SETUP"] = "1"

    def tearDown(self):
        for key, value in (("HOME", self.old_home), ("LAZYPLAN_NO_SETUP", self.old_setup)):
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()

    def _run(self, *argv: str) -> tuple[int, str, str]:
        out = io.StringIO()
        err = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = lpui_main(["--db", self.db, "--actor", "alice", *argv])
        return code, out.getvalue(), err.getvalue()

    def test_relate_and_unrelate_json(self):
        code, out, err = self._run("--json", "criterion", "relate", "--id", "1", "--task", "1")
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["link"]["task"], "T")
        self.assertEqual(Store(self.db).criterion_tasks(1)[0].id, 1)

        code, out, err = self._run("--json", "criterion", "unrelate", "--id", "1", "--task", "1")
        self.assertEqual(code, 0, err)
        self.assertFalse(json.loads(out)["link"]["linked"])
        self.assertEqual(Store(self.db).criterion_tasks(1), [])

    def test_relate_porcelain(self):
        code, out, err = self._run("--porcelain", "criterion", "relate", "--id", "1", "--task", "1")
        self.assertEqual(code, 0, err)
        self.assertEqual(
            out.rstrip("\n").split("\t"),
            ["link", "1", "linked", "T", "criterion:1", "task:1"],
        )

    def test_duplicate_and_missing_exit_one(self):
        self.assertEqual(self._run("criterion", "relate", "--id", "1", "--task", "1")[0], 0)
        code, out, err = self._run("criterion", "relate", "--id", "1", "--task", "1")
        self.assertEqual(code, 1)
        self.assertIn("already linked", err)
        code, out, err = self._run("criterion", "relate", "--id", "99", "--task", "1")
        self.assertEqual(code, 1)
        self.assertIn("criterion 99", err)


if __name__ == "__main__":
    unittest.main()
