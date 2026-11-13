import os
import tempfile
import unittest

from lazyplan.store import Store


class TestPlanWorktrees(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(os.path.join(self.tmp.name, "worktrees.db"))
        self.plan = self.store.add_plan("Plan 6", description="", goal="")
        self.repo = os.path.join(self.tmp.name, "repo")
        self.worktree = os.path.join(self.tmp.name, "repo--plan-6")

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
        self.assertEqual(row.repo_path, os.path.abspath(self.repo))
        self.assertEqual(row.worktree_path, os.path.abspath(self.worktree))
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
        self.assertEqual(second.worktree_path, os.path.abspath(self.worktree + "-moved"))
        self.assertEqual(len(self.store.list_plan_worktrees(self.plan.id)), 1)

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

    def test_deleting_a_plan_removes_its_worktrees(self):
        self.store.register_plan_worktree(self.plan.id, self.repo, self.worktree)

        self.assertTrue(self.store.delete("plan", self.plan.id))

        self.assertEqual(self.store.list_plan_worktrees(self.plan.id), [])
