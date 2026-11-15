"""Lane gates: claims, next, plan starts, and doctor findings."""

from __future__ import annotations

import os
import tempfile
import unittest

from lazyplan.core.entities import Status
from lazyplan.services import coordination, planning
from lazyplan.services.worktrees import lane_gate, worktree_gate
from lazyplan.store import Store


class LaneGateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = os.path.realpath(self.tmp.name)
        self.store = Store(os.path.join(self.root, "lanes.db"))
        self.old_cwd = os.getcwd()
        self.plan = self.store.add_plan("Lanes", dispatch_mode="parallel", max_agents=2)
        self.repo = os.path.join(self.root, "repo")
        os.makedirs(self.repo)
        self.store.add_repo_link("plan", self.plan.id, self.repo)
        self.milestones = []
        self.tasks = []
        for title in ("A", "B"):
            milestone = self.store.add_milestone(self.plan.id, title, lane_group=1)
            task = self.store.add_task(
                milestone.id, f"Work {title}", "Commit: one.\n\nVerify: tests."
            )
            self.milestones.append(milestone)
            self.tasks.append(task)
        self.paths = []
        for index, milestone in enumerate(self.milestones):
            path = os.path.join(self.root, f"repo--lane-{index}")
            os.makedirs(path)
            self.store.register_plan_worktree(
                self.plan.id,
                self.repo,
                path,
                branch=f"lane-{index}",
                milestone_id=milestone.id,
            )
            self.paths.append(path)

    def tearDown(self) -> None:
        os.chdir(self.old_cwd)
        self.tmp.cleanup()

    def test_correct_lane_passes(self) -> None:
        self.assertEqual(lane_gate(self.store, self.tasks[0].id, self.paths[0]), "")

    def test_wrong_lane_is_refused_by_name(self) -> None:
        blocker = lane_gate(self.store, self.tasks[0].id, self.paths[1])
        self.assertIn("belongs to lane M1", blocker)

    def test_shared_checkout_is_refused(self) -> None:
        blocker = lane_gate(self.store, self.tasks[0].id, self.repo)
        self.assertIn("must run in lane M1", blocker)

    def test_missing_lane_registration_names_the_command(self) -> None:
        extra = self.store.add_milestone(self.plan.id, "C", lane_group=2)
        task = self.store.add_task(extra.id, "Work C", "Commit: one.\n\nVerify: tests.")
        blocker = lane_gate(self.store, task.id, self.repo)
        self.assertIn("has no registered worktree", blocker)
        self.assertIn(f"--milestone {extra.id}", blocker)

    def test_serial_plan_ignores_lanes(self) -> None:
        plan = self.store.add_plan("Serial", dispatch_mode="serial", max_agents=1)
        milestone = self.store.add_milestone(plan.id, "Only")
        task = self.store.add_task(milestone.id, "Work", "Commit: one.\n\nVerify: tests.")
        self.assertEqual(lane_gate(self.store, task.id, self.repo), "")

    def test_worktree_gate_requires_every_lane(self) -> None:
        self.assertEqual(worktree_gate(self.store, self.plan.id), "")
        self.store.remove_plan_worktree(self.plan.id, self.repo, milestone_id=self.milestones[1].id)
        blocker = worktree_gate(self.store, self.plan.id)
        self.assertIn(f"M{self.milestones[1].id}", blocker)
        self.assertIn("--milestone", blocker)

    def test_explicit_claim_refuses_the_wrong_lane(self) -> None:
        with self.assertRaisesRegex(ValueError, "belongs to lane M1"):
            coordination.start_claim(
                self.store,
                self.tasks[0].id,
                "worker",
                worktree=self.paths[1],
            )

    def test_forced_claim_records_the_override(self) -> None:
        result = coordination.start_claim(
            self.store,
            self.tasks[0].id,
            "worker",
            worktree=self.paths[1],
            force=True,
            reason="handoff to the integration lane",
        )
        self.assertEqual(result["claim"]["task_id"], self.tasks[0].id)

    def test_next_stays_inside_the_current_lane(self) -> None:
        result = coordination.claim_next(
            self.store, "worker", plan_id=self.plan.id, worktree=self.paths[1]
        )
        assert result is not None
        self.assertEqual(result["task"]["id"], self.tasks[1].id)

    def test_task_move_refuses_a_checkout_in_another_lane(self) -> None:
        os.chdir(self.paths[1])
        with self.assertRaisesRegex(ValueError, "belongs to lane M1"):
            planning.set_status(self.store, "task", self.tasks[0].id, Status.DOING, actor="worker")
        os.chdir(self.paths[0])
        self.assertTrue(
            planning.set_status(self.store, "task", self.tasks[0].id, Status.DOING, actor="worker")
        )


if __name__ == "__main__":
    unittest.main()
