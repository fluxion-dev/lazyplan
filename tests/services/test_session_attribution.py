"""Session attribution: branch, plan, and task resolution."""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from lazyplan.core.entities import Status
from lazyplan.services import set_status
from lazyplan.services.attribution import current_branch, resolve
from lazyplan.store import Store


class AttributionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self._git("init", "-b", "main")
        self._git("config", "user.email", "test@example.com")
        self._git("config", "user.name", "Test")
        (self.repo / "file.txt").write_text("one\n", encoding="utf-8")
        self._git("add", "file.txt")
        self._git("commit", "-m", "init")
        self.store = Store(os.path.join(self.tmp.name, "t.db"))
        self.plan = self.store.add_plan("Pane plan", actor="ana")
        self.milestone = self.store.add_milestone(self.plan.id, "Pane milestone", actor="ana")
        self.task = self.store.add_task(self.milestone.id, "Pane task", actor="ana")
        self.store.add_repo_link("plan", self.plan.id, str(self.repo), actor="ana")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _git(self, *args: str) -> None:
        subprocess.run(
            ["git", *args],
            cwd=self.repo,
            check=True,
            capture_output=True,
        )

    def _doing_plan(self, title: str) -> tuple[int, int]:
        plan = self.store.add_plan(title, actor="ana")
        milestone = self.store.add_milestone(plan.id, f"{title} milestone", actor="ana")
        task = self.store.add_task(milestone.id, f"{title} task", actor="ana")
        set_status(self.store, "task", task.id, Status.DOING, actor="ana")
        self.store.add_repo_link("plan", plan.id, str(self.repo), actor="ana")
        return plan.id, task.id

    def test_current_branch_reads_git_and_detached_head_is_empty(self) -> None:
        self._git("switch", "-c", "task/165-pane")
        self.assertEqual(current_branch(str(self.repo)), "task/165-pane")
        self._git("checkout", "--detach")
        self.assertEqual(current_branch(str(self.repo)), "")

    def test_branch_ref_resolves_plan_and_task(self) -> None:
        self._git("switch", "-c", f"task/{self.task.id}-pane")
        found = resolve(self.store, str(self.repo), f"task/{self.task.id}-pane")
        self.assertEqual(found.plan_id, self.plan.id)
        self.assertEqual(found.task_id, self.task.id)

    def test_unknown_branch_ref_falls_through(self) -> None:
        found = resolve(self.store, str(self.repo), "task/ninety-nine")
        self.assertIsNone(found.plan_id)

    def test_recorded_branch_beats_a_claim(self) -> None:
        other_plan, other_task = self._doing_plan("Other plan")
        self.store.add_repo_link(
            "task",
            other_task,
            str(self.repo),
            branch="feat/custom",
            actor="ana",
        )
        self.store.claim_task(self.task.id, "ana", repo_path=str(self.repo))
        found = resolve(self.store, str(self.repo), "feat/custom")
        self.assertEqual(found.plan_id, other_plan)
        self.assertEqual(found.task_id, other_task)

    def test_claim_resolves_an_unmapped_branch(self) -> None:
        self.store.claim_task(self.task.id, "ana", repo_path=str(self.repo))
        found = resolve(self.store, str(self.repo), "feat/plain")
        self.assertEqual(found.plan_id, self.plan.id)
        self.assertEqual(found.task_id, self.task.id)

    def test_single_doing_plan_scoped_to_the_checkout(self) -> None:
        doing_plan, _task = self._doing_plan("Doing plan")
        found = resolve(self.store, str(self.repo), "feat/plain")
        self.assertEqual(found.plan_id, doing_plan)

    def test_two_doing_plans_are_ambiguous(self) -> None:
        self._doing_plan("First doing")
        self._doing_plan("Second doing")
        found = resolve(self.store, str(self.repo), "feat/plain")
        self.assertIsNone(found.plan_id)

    def test_another_checkout_never_leaks(self) -> None:
        other = self.root / "other"
        other.mkdir()
        plan = self.store.add_plan("Other plan", actor="ana")
        milestone = self.store.add_milestone(plan.id, "Other milestone", actor="ana")
        task = self.store.add_task(milestone.id, "Other task", actor="ana")
        set_status(self.store, "task", task.id, Status.DOING, actor="ana")
        self.store.add_repo_link("plan", plan.id, str(other), actor="ana")
        self.store.claim_task(task.id, "ana", repo_path=str(other))
        found = resolve(self.store, str(self.repo), "feat/plain")
        self.assertIsNone(found.plan_id)
        self.assertIsNone(found.task_id)

    def test_explicit_plan_wins(self) -> None:
        found = resolve(self.store, str(self.repo), "feat/plain", explicit_plan=self.plan.id)
        self.assertEqual(found.plan_id, self.plan.id)
        self.assertIsNone(found.task_id)
