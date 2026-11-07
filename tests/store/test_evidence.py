"""Store persistence for the criterion evidence ledger."""

from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from contextlib import closing

from lazyplan.store import Store
from lazyplan.store import migrate as migrate_mod


class TestEvidenceStore(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "t.db")
        self.store = Store(self.db)
        self.plan = self.store.add_plan("Plan")
        self.milestone = self.store.add_milestone(self.plan.id, "M")
        self.task = self.store.add_task(self.milestone.id, "T")
        self.criterion = self.store.add_criteria("task", self.task.id, "Works")
        self.store.relate_criterion(self.criterion.id, self.task.id)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_schema_has_evidence_table_and_indexes(self) -> None:
        with closing(sqlite3.connect(self.db)) as conn:
            self.assertEqual(
                int(conn.execute("PRAGMA user_version").fetchone()[0]),
                migrate_mod.SCHEMA_VERSION,
            )
            names = {
                str(row[0])
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")
            }
        self.assertIn("idx_criterion_evidence_criterion", names)
        self.assertIn("idx_criterion_evidence_task", names)

    def test_add_and_list_evidence(self) -> None:
        row = self.store.add_evidence(
            self.criterion.id,
            command="pytest tests/store",
            exit_code=0,
            commit_sha="A" * 40,
            pr_url="https://github.com/o/r/pull/1",
            artifact_path="reports/unit.xml",
            note="local run",
            task_id=self.task.id,
            actor="ci",
        )
        self.assertEqual(row.commit_sha, "a" * 40)
        self.assertEqual(row.actor, "ci")
        self.assertGreater(row.ts, 0)
        self.assertTrue(row.passing)
        rows = self.store.list_evidence(self.criterion.id)
        self.assertEqual([item.id for item in rows], [row.id])
        self.assertEqual(
            self.store.evidence_map()[self.criterion.id][0].command, "pytest tests/store"
        )

    def test_unrelated_task_is_rejected(self) -> None:
        other = self.store.add_task(self.milestone.id, "Other")
        with self.assertRaises(ValueError):
            self.store.add_evidence(self.criterion.id, command="pytest", task_id=other.id)

    def test_missing_criterion_and_task_are_rejected(self) -> None:
        with self.assertRaises(KeyError):
            self.store.add_evidence(999_999, command="pytest")
        with self.assertRaises(KeyError):
            self.store.add_evidence(self.criterion.id, command="pytest", task_id=999_999)

    def test_empty_evidence_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.store.add_evidence(self.criterion.id)

    def test_failing_evidence_is_recorded(self) -> None:
        row = self.store.add_evidence(self.criterion.id, command="pytest", exit_code=1)
        self.assertFalse(row.passing)

    def test_criterion_delete_cascades_evidence(self) -> None:
        self.store.add_evidence(self.criterion.id, command="pytest")
        self.store.delete_criteria(self.criterion.id)
        self.assertEqual(self.store.list_evidence(self.criterion.id), [])

    def test_task_delete_keeps_evidence_with_null_task(self) -> None:
        criterion = self.store.add_criteria("plan", self.plan.id, "Ships")
        self.store.relate_criterion(criterion.id, self.task.id)
        self.store.add_evidence(criterion.id, command="pytest", task_id=self.task.id)
        self.store.delete("task", self.task.id)
        rows = self.store.list_evidence(criterion.id)
        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0].task_id)

    def test_full_payloads_carry_evidence_summary(self) -> None:
        self.store.add_evidence(self.criterion.id, command="pytest")
        task = self.store.get_full("task", self.task.id)
        assert task is not None
        evidence = task["criteria"][0]["evidence"]
        self.assertEqual(evidence["count"], 1)
        self.assertEqual(evidence["state"], "pass")
        self.assertEqual(evidence["latest"]["command"], "pytest")

        plan_criterion = self.store.add_criteria("plan", self.plan.id, "Ships")
        self.store.add_evidence(plan_criterion.id, note="reviewed")
        plan = self.store.get_full("plan", self.plan.id)
        assert plan is not None
        self.assertEqual(plan["criteria"][0]["evidence"]["state"], "pass")

    def test_v3_database_gains_the_evidence_table(self) -> None:
        path = os.path.join(self.tmp.name, "v3.db")
        with closing(sqlite3.connect(path)) as conn:
            conn.executescript(migrate_mod.SCHEMA)
            conn.execute("DROP TABLE criterion_evidence")
            conn.execute("PRAGMA user_version = 3")
            conn.execute(
                "INSERT INTO plans (name, description, status, goal, uid)"
                " VALUES ('Old', '', 'todo', '', 'uid-old')"
            )
            conn.commit()
        store = Store(path)
        self.assertEqual(store.list_plans()[0].name, "Old")
        criterion = store.add_criteria("plan", store.list_plans()[0].id, "Works")
        self.assertEqual(store.add_evidence(criterion.id, command="pytest").command, "pytest")


if __name__ == "__main__":
    unittest.main()
