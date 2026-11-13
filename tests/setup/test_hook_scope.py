"""Managed-checkout scope: only linked or local checkouts are gated."""

import tempfile
import unittest
from pathlib import Path

from lazyplan import services
from lazyplan.core.entities import Status
from lazyplan.services import hook_policy, hook_scope
from lazyplan.store import Store


class ScopeCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.repo = root / "repo"
        self.repo.mkdir()
        self.other = root / "other"
        self.other.mkdir()
        self.home = root / "home"
        self.home.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def _seed(self, store: Store, linked: Path | None = None) -> tuple[int, int]:
        plan = store.add_plan("P", "what", goal="why")
        milestone = store.add_milestone(plan.id, "M", "desc")
        task = store.add_task(milestone.id, "Doing task", "desc")
        services.set_status(store, "task", task.id, Status.DOING, actor="t")
        services.set_status(store, "milestone", milestone.id, Status.DOING, actor="t")
        services.set_status(store, "plan", plan.id, Status.DOING, actor="t")
        if linked is not None:
            store.add_repo_link("plan", plan.id, str(linked), actor="t")
        return plan.id, task.id

    def test_global_database_in_an_unrelated_repo_is_unmanaged(self):
        store = Store(self.home / ".lazyplan/lazyplan.db")
        self._seed(store)
        scope = hook_scope.resolve(store, self.repo)
        self.assertFalse(scope.managed)
        self.assertIsNone(scope.task)

    def test_repo_scoped_database_is_managed(self):
        store = Store(self.repo / ".agents/lazyplan/lazyplan.db")
        _plan, task_id = self._seed(store)
        scope = hook_scope.resolve(store, self.repo)
        self.assertTrue(scope.managed)
        self.assertEqual(scope.task_id, task_id)

    def test_a_linked_plan_makes_a_global_database_managed(self):
        store = Store(self.home / ".lazyplan/lazyplan.db")
        _plan, task_id = self._seed(store, linked=self.repo)
        scope = hook_scope.resolve(store, self.repo)
        self.assertTrue(scope.managed)
        self.assertEqual(scope.task_id, task_id)
        self.assertFalse(hook_scope.resolve(store, self.other).managed)

    def test_a_linked_plan_without_doing_work_has_no_task(self):
        store = Store(self.home / ".lazyplan/lazyplan.db")
        plan = store.add_plan("P")
        store.add_repo_link("plan", plan.id, str(self.repo), actor="t")
        scope = hook_scope.resolve(store, self.repo)
        self.assertTrue(scope.managed)
        self.assertIsNone(scope.task)

    def test_an_isolated_plan_gates_only_its_registered_worktree(self):
        store = Store(self.home / ".lazyplan/lazyplan.db")
        plan_id, task_id = self._seed(store, linked=self.repo)
        store.register_plan_worktree(plan_id, str(self.repo), str(self.other), branch="plan/1")

        shared = hook_scope.resolve(store, self.repo)
        self.assertFalse(shared.managed)
        self.assertIsNone(shared.task)

        inside = hook_scope.resolve(store, self.other)
        self.assertTrue(inside.managed)
        self.assertEqual(inside.task_id, task_id)

        blocked = hook_policy.commit_result(store, self.repo, "git commit -m x", "strict")
        self.assertEqual(blocked.block, "")

    def test_a_live_claim_in_this_checkout_makes_it_managed(self):
        store = Store(self.home / ".lazyplan/lazyplan.db")
        _plan, task_id = self._seed(store)
        store.claim_task(task_id, "t", worktree=str(self.repo), repo_path=str(self.repo))
        self.assertTrue(hook_scope.resolve(store, self.repo).managed)
        self.assertFalse(hook_scope.resolve(store, self.other).managed)

    def test_an_expired_claim_leaves_the_checkout_unmanaged(self):
        store = Store(self.home / ".lazyplan/lazyplan.db")
        _plan, task_id = self._seed(store)
        store.claim_task(
            task_id, "t", ttl_seconds=1, now=0, worktree=str(self.repo), repo_path=str(self.repo)
        )
        self.assertFalse(hook_scope.resolve(store, self.repo).managed)


if __name__ == "__main__":
    unittest.main()
