"""Dispatch manifest: waves, capacity, readiness, actions, and prompts."""

from __future__ import annotations

import os
import tempfile
import unittest

from lazyplan.core.entities import Status
from lazyplan.services import dispatch
from lazyplan.store import Store


class DispatchManifestTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = os.path.realpath(self.tmp.name)
        self.store = Store(os.path.join(self.root, "dispatch.db"))
        self.repo = os.path.join(self.root, "repo")
        os.makedirs(self.repo)
        self.plan = self.store.add_plan("Lanes", dispatch_mode="parallel", max_agents=2)
        self.store.add_repo_link("plan", self.plan.id, self.repo)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _lane(
        self,
        title: str,
        group: int,
        role: str = "implementer",
        tasks: int = 1,
    ) -> tuple[int, list[int]]:
        milestone = self.store.add_milestone(self.plan.id, title, lane_group=group, agent_role=role)
        ids = [
            self.store.add_task(
                milestone.id,
                f"{title} work {index}",
                f"Approach: do {title}.\n\nCommit: one slice.\n\nVerify: tests.",
                role="qa" if index == 0 else "implementer",
            ).id
            for index in range(tasks)
        ]
        return milestone.id, ids

    def _register(self, milestone_id: int, title: str) -> str:
        path = os.path.join(self.root, f"repo--{title}")
        os.makedirs(path, exist_ok=True)
        self.store.register_plan_worktree(
            self.plan.id,
            self.repo,
            path,
            branch=f"plan/{title}",
            milestone_id=milestone_id,
        )
        return path

    def _parallel_plan(self) -> tuple[list[int], list[int]]:
        lane_a, tasks_a = self._lane("Alpha", 1)
        lane_b, tasks_b = self._lane("Beta", 1)
        integrator, tasks_c = self._lane("Integrate", 2, role="integrator")
        self._register(lane_a, "alpha")
        self._register(lane_b, "beta")
        self._register(integrator, "integrate")
        return [lane_a, lane_b, integrator], tasks_a + tasks_b + tasks_c

    def test_states_capacity_and_dispatchable_tasks(self) -> None:
        lanes, tasks = self._parallel_plan()
        manifest = dispatch.build(self.store, self.plan.id)

        self.assertEqual(manifest["wave"], 1)
        self.assertEqual(manifest["capacity"], {"max": 2, "active": 0, "available": 2})
        states = {lane["milestone_id"]: lane["state"] for lane in manifest["lanes"]}
        self.assertEqual(states[lanes[0]], "ready")
        self.assertEqual(states[lanes[1]], "ready")
        self.assertEqual(states[lanes[2]], "waiting")
        self.assertEqual(
            [item["task_id"] for item in manifest["dispatchable"]],
            [tasks[0], tasks[1]],
        )
        for item in manifest["dispatchable"]:
            self.assertIn(f"T{item['task_id']}", item["prompt"])
            self.assertIn("Commit small green slices", item["prompt"])
            self.assertTrue(item["claim_command"])
            self.assertIn("tier", item["profile"])

    def test_manifest_includes_resolved_profiles(self) -> None:
        self._parallel_plan()
        manifest = dispatch.build(self.store, self.plan.id)
        self.assertIn("implementer", manifest["profiles"])
        self.assertEqual(manifest["profiles"]["reviewer"]["claude"], "opus")
        self.assertEqual(manifest["profiles"]["implementer"]["tier"], "fast")

    def test_missing_lane_worktree_becomes_an_action(self) -> None:
        lanes, tasks = self._parallel_plan()
        self.store.remove_plan_worktree(self.plan.id, self.repo, milestone_id=lanes[1])
        manifest = dispatch.build(self.store, self.plan.id)
        beta = next(lane for lane in manifest["lanes"] if lane["milestone_id"] == lanes[1])
        self.assertEqual(beta["state"], "unregistered")
        self.assertTrue(any("worktree is not registered" in item for item in beta["blocked"]))
        self.assertEqual([item["task_id"] for item in manifest["dispatchable"]], [tasks[0]])
        self.assertTrue(any(f"--milestone {lanes[1]}" in action for action in manifest["actions"]))

    def test_one_lane_filter(self) -> None:
        lanes, _ = self._parallel_plan()
        manifest = dispatch.build(self.store, self.plan.id, lane_id=lanes[1])
        self.assertEqual([lane["milestone_id"] for lane in manifest["lanes"]], [lanes[1]])
        self.assertEqual(len(manifest["dispatchable"]), 1)

    def test_serial_plan_waits_for_the_first_milestone(self) -> None:
        plan = self.store.add_plan("Serial", dispatch_mode="serial", max_agents=1)
        self.store.add_repo_link("plan", plan.id, self.repo)
        first = self.store.add_milestone(plan.id, "First", lane_group=1)
        second = self.store.add_milestone(plan.id, "Second", lane_group=2)
        for milestone in (first, second):
            self.store.add_task(milestone.id, "Work", "Commit: one.\n\nVerify: tests.")
        plan_path = os.path.join(self.root, "repo--serial")
        os.makedirs(plan_path, exist_ok=True)
        self.store.register_plan_worktree(plan.id, self.repo, plan_path, branch="plan/serial")
        manifest = dispatch.build(self.store, plan.id)
        self.assertEqual(manifest["capacity"]["max"], 1)
        states = {lane["milestone_id"]: lane["state"] for lane in manifest["lanes"]}
        self.assertEqual(states[first.id], "ready")
        self.assertEqual(states[second.id], "waiting")
        self.assertEqual(len(manifest["dispatchable"]), 1)

    def test_active_claim_reduces_available_capacity(self) -> None:
        lanes, tasks = self._parallel_plan()
        self.store.claim_task(tasks[0], "worker", ttl_seconds=1800, worktree="lane-a")
        self.store.set_status_raw("task", tasks[0], Status.DOING)
        manifest = dispatch.build(self.store, self.plan.id)
        self.assertEqual(manifest["capacity"]["active"], 1)
        self.assertEqual(manifest["capacity"]["available"], 1)
        self.assertEqual([item["task_id"] for item in manifest["dispatchable"]], [tasks[1]])

    def test_build_is_read_only(self) -> None:
        self._parallel_plan()
        before = len(self.store.feed(limit=10_000))
        dispatch.build(self.store, self.plan.id)
        self.assertEqual(len(self.store.feed(limit=10_000)), before)

    def test_prompt_honors_the_budget(self) -> None:
        lanes, _ = self._parallel_plan()
        manifest = dispatch.build(self.store, self.plan.id, lane_id=lanes[0], max_chars=120)
        (item,) = manifest["dispatchable"]
        self.assertLessEqual(len(item["prompt"]), 120)
        self.assertTrue(item["prompt"].endswith("…"))

    def test_missing_plan_raises(self) -> None:
        with self.assertRaises(KeyError):
            dispatch.build(self.store, 999)

    def test_foreign_lane_raises(self) -> None:
        other = self.store.add_plan("Other")
        foreign = self.store.add_milestone(other.id, "Foreign")
        with self.assertRaises(ValueError):
            dispatch.build(self.store, self.plan.id, lane_id=foreign.id)

    def test_not_doing_plan_is_blocked(self) -> None:
        self._parallel_plan()
        self.store.set_status_raw("task", 1, Status.DONE)
        manifest = dispatch.build(self.store, self.plan.id)
        self.assertTrue(manifest["blocked"])
        self.assertIn("not doing", manifest["blocked"][0])


if __name__ == "__main__":
    unittest.main()
