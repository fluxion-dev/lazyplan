"""Store persistence for task touch-points and claim locations."""

from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from contextlib import closing

from lazyplan.store import Store
from lazyplan.store import migrate as migrate_mod


class TestTouchpointsStore(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "t.db")
        self.store = Store(self.db)
        self.plan = self.store.add_plan("Plan")
        self.milestone = self.store.add_milestone(self.plan.id, "M")
        self.task = self.store.add_task(self.milestone.id, "T")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_schema_has_touchpoints_and_claim_location(self) -> None:
        with closing(sqlite3.connect(self.db)) as conn:
            self.assertEqual(
                int(conn.execute("PRAGMA user_version").fetchone()[0]),
                migrate_mod.SCHEMA_VERSION,
            )
            names = {
                str(row[0])
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")
            }
            columns = {
                str(row[1]) for row in conn.execute("PRAGMA table_info(task_claims)").fetchall()
            }
        self.assertIn("idx_task_touchpoints_task", names)
        self.assertIn("worktree", columns)
        self.assertIn("repo_path", columns)

    def test_add_is_idempotent_and_list_is_sorted(self) -> None:
        self.store.add_touchpoint(self.task.id, "./src//store/")
        self.store.add_touchpoint(self.task.id, "src/store")
        self.store.add_touchpoint(self.task.id, "tests/*.py")
        self.assertEqual(self.store.list_touchpoints(self.task.id), ["src/store", "tests/*.py"])
        self.assertEqual(self.store.touchpoints_map()[self.task.id], ["src/store", "tests/*.py"])

    def test_remove_and_cascade(self) -> None:
        self.store.add_touchpoint(self.task.id, "src/store")
        self.assertTrue(self.store.remove_touchpoint(self.task.id, "src/store"))
        self.assertFalse(self.store.remove_touchpoint(self.task.id, "src/store"))
        self.store.add_touchpoint(self.task.id, "src/tui")
        self.store.delete("task", self.task.id)
        self.assertEqual(self.store.list_touchpoints(self.task.id), [])

    def test_invalid_paths_and_missing_task(self) -> None:
        with self.assertRaises(ValueError):
            self.store.add_touchpoint(self.task.id, "../outside")
        with self.assertRaises(KeyError):
            self.store.add_touchpoint(999, "src/store")

    def test_claim_records_worktree_and_repo(self) -> None:
        claim, _previous = self.store.claim_task(
            self.task.id, "ana", worktree="/repo/wt", repo_path="/repo"
        )
        self.assertEqual(claim.worktree, "/repo/wt")
        self.assertEqual(claim.repo_path, "/repo")
        row = self.store.list_claims()[0]
        self.assertEqual(row["worktree"], "/repo/wt")
        self.assertEqual(row["repo_path"], "/repo")

    def test_v6_database_gains_touchpoints(self) -> None:
        path = os.path.join(self.tmp.name, "v6.db")
        with closing(sqlite3.connect(path)) as conn:
            conn.executescript(migrate_mod.SCHEMA)
            conn.execute("DROP TABLE task_touchpoints")
            conn.execute("ALTER TABLE task_claims DROP COLUMN worktree")
            conn.execute("ALTER TABLE task_claims DROP COLUMN repo_path")
            conn.execute("PRAGMA user_version = 6")
            conn.execute(
                "INSERT INTO plans (name, description, status, goal, uid)"
                " VALUES ('Old', '', 'todo', '', 'uid-old')"
            )
            conn.execute("INSERT INTO milestones (plan_id, title) VALUES (1, 'M')")
            conn.execute("INSERT INTO tasks (milestone_id, title) VALUES (1, 'T')")
            conn.commit()
        store = Store(path)
        store.add_touchpoint(1, "src/store")
        self.assertEqual(store.list_touchpoints(1), ["src/store"])


if __name__ == "__main__":
    unittest.main()
