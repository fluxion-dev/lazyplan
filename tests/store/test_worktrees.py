import os
import sqlite3
import tempfile
import unittest
from contextlib import closing

from lazyplan.store import Store
from lazyplan.store import migrate as migrate_mod


class TestPlanWorktrees(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(os.path.join(self.tmp.name, "worktrees.db"))
        self.plan = self.store.add_plan("Plan 6", description="", goal="")
        self.repo = os.path.realpath(os.path.join(self.tmp.name, "repo"))
        self.worktree = os.path.realpath(os.path.join(self.tmp.name, "repo--plan-6"))

    def tearDown(self):
        self.tmp.cleanup()

    def test_register_round_trips_and_lists(self):
        row = self.store.register_plan_worktree(
            self.plan.id,
            self.repo,
            self.worktree,
            branch="plan/6-plan-worktrees",
            repo_remote="https://example.test/repo.git",
            registered_at=123.0,
        )

        self.assertEqual(row.plan_id, self.plan.id)
        self.assertEqual(row.repo_path, os.path.realpath(self.repo))
        self.assertEqual(row.worktree_path, os.path.realpath(self.worktree))
        self.assertEqual(row.branch, "plan/6-plan-worktrees")
        self.assertEqual(row.repo_remote, "https://example.test/repo.git")
        self.assertEqual(row.registered_at, 123.0)
        self.assertEqual(self.store.list_plan_worktrees(self.plan.id), [row])
        self.assertEqual(self.store.get_plan_worktree(self.plan.id, self.repo), row)

    def test_reregister_updates_one_row(self):
        first = self.store.register_plan_worktree(
            self.plan.id, self.repo, self.worktree, branch="old", registered_at=1.0
        )
        second = self.store.register_plan_worktree(
            self.plan.id,
            self.repo,
            self.worktree + "-moved",
            branch="new",
            registered_at=2.0,
        )

        self.assertEqual(second.id, first.id)
        self.assertEqual(second.branch, "new")
        self.assertEqual(second.worktree_path, os.path.realpath(self.worktree + "-moved"))
        self.assertEqual(len(self.store.list_plan_worktrees(self.plan.id)), 1)

    def test_registration_survives_reopen(self):
        row = self.store.register_plan_worktree(
            self.plan.id, self.repo, self.worktree, branch="plan/6-test"
        )

        reopened = Store(self.store.path)

        self.assertEqual(reopened.list_plan_worktrees(self.plan.id), [row])

    def test_remove_reports_whether_a_row_existed(self):
        self.store.register_plan_worktree(self.plan.id, self.repo, self.worktree)

        self.assertTrue(self.store.remove_plan_worktree(self.plan.id, self.repo))
        self.assertFalse(self.store.remove_plan_worktree(self.plan.id, self.repo))
        self.assertEqual(self.store.list_plan_worktrees(self.plan.id), [])

    def test_register_refuses_unknown_plan_and_empty_paths(self):
        with self.assertRaises(KeyError):
            self.store.register_plan_worktree(999, self.repo, self.worktree)
        with self.assertRaises(ValueError):
            self.store.register_plan_worktree(self.plan.id, self.repo, "")

    def test_one_worktree_per_lane_in_the_same_repo(self):
        lane_a = self.store.add_milestone(self.plan.id, "Lane A")
        lane_b = self.store.add_milestone(self.plan.id, "Lane B")
        plan_row = self.store.register_plan_worktree(
            self.plan.id, self.repo, self.worktree, branch="plan/6"
        )
        a = self.store.register_plan_worktree(
            self.plan.id,
            self.repo,
            self.worktree + "-a",
            branch="plan/6--a",
            milestone_id=lane_a.id,
        )
        b = self.store.register_plan_worktree(
            self.plan.id,
            self.repo,
            self.worktree + "-b",
            branch="plan/6--b",
            milestone_id=lane_b.id,
        )

        rows = self.store.list_plan_worktrees(self.plan.id)
        self.assertEqual({row.id for row in rows}, {plan_row.id, a.id, b.id})
        self.assertEqual(self.store.get_plan_worktree(self.plan.id, self.repo), plan_row)
        self.assertEqual(self.store.get_plan_worktree(self.plan.id, self.repo, lane_a.id), a)
        self.assertIsNone(self.store.get_plan_worktree(self.plan.id, self.repo, lane_b.id + 1))

        self.assertTrue(
            self.store.remove_plan_worktree(self.plan.id, self.repo, milestone_id=lane_a.id)
        )
        self.assertEqual(len(self.store.list_plan_worktrees(self.plan.id)), 2)

    def test_lane_registration_refuses_a_foreign_milestone(self):
        other = self.store.add_plan("Other")
        foreign = self.store.add_milestone(other.id, "Foreign")
        with self.assertRaises(ValueError):
            self.store.register_plan_worktree(
                self.plan.id, self.repo, self.worktree, milestone_id=foreign.id
            )
        with self.assertRaises(KeyError):
            self.store.register_plan_worktree(
                self.plan.id, self.repo, self.worktree, milestone_id=999
            )

    def test_legacy_registry_gains_a_lane_column(self):
        lane = self.store.add_milestone(self.plan.id, "Lane")
        self.store.register_plan_worktree(self.plan.id, self.repo, self.worktree, branch="plan/6")
        with closing(sqlite3.connect(self.store.path)) as conn:
            conn.execute("DROP INDEX IF EXISTS idx_plan_worktrees_plan_repo")
            conn.execute("DROP INDEX IF EXISTS idx_plan_worktrees_lane")
            conn.execute("DROP INDEX IF EXISTS idx_plan_worktrees_milestone")
            conn.execute("ALTER TABLE plan_worktrees DROP COLUMN milestone_id")
            conn.execute(f"PRAGMA user_version = {migrate_mod.SCHEMA_VERSION - 1}")
            conn.commit()

        reopened = Store(self.store.path)
        rows = reopened.list_plan_worktrees(self.plan.id)
        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0].milestone_id)
        lane_row = reopened.register_plan_worktree(
            self.plan.id,
            self.repo,
            self.worktree + "-lane",
            branch="plan/6--lane",
            milestone_id=lane.id,
        )
        self.assertEqual(lane_row.milestone_id, lane.id)
        self.assertEqual(len(reopened.list_plan_worktrees(self.plan.id)), 2)

    def test_deleting_a_plan_removes_its_worktrees(self):
        self.store.register_plan_worktree(self.plan.id, self.repo, self.worktree)

        self.assertTrue(self.store.delete("plan", self.plan.id))

        self.assertEqual(self.store.list_plan_worktrees(self.plan.id), [])
