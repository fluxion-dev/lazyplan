"""Lane flags on plan, milestone, and task writes, plus their rendered labels."""

from __future__ import annotations

import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout

from lazyplan.presentation.cli.main import main as lpui_main
from lazyplan.store import Store


class LaneCliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "lanes.db")
        self.env = {"LAZYPLAN_NO_SETUP": "1", "LAZYPLAN_NO_UPDATE_CHECK": "1"}
        self.saved = {key: os.environ.get(key) for key in self.env}
        os.environ.update(self.env)

    def tearDown(self) -> None:
        for key, value in self.saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()

    def _run(self, argv: list[str]) -> tuple[int, str]:
        out = io.StringIO()
        with redirect_stdout(out):
            code = lpui_main(["--db", self.db, *argv])
        return code, out.getvalue()

    def _plan(self) -> tuple[int, str]:
        return self._run(
            [
                "plan",
                "add",
                "--title",
                "Lanes",
                "--why",
                "Ship in waves.",
                "--what",
                "## Scope\n\n- Two lanes.",
                "--dispatch",
                "parallel",
                "--max-agents",
                "3",
            ]
        )

    def test_plan_lane_flags_persist(self) -> None:
        code, _ = self._plan()
        self.assertEqual(code, 0)
        plan = Store(self.db).get_plan(1)
        self.assertEqual((plan.dispatch_mode, plan.max_agents), ("parallel", 3))

    def test_milestone_and_task_lane_flags_persist(self) -> None:
        self._plan()
        code, _ = self._run(
            [
                "milestone",
                "add",
                "--plan",
                "1",
                "--title",
                "Build it",
                "--desc",
                "As a user, I want the slice.",
                "--lane-group",
                "2",
                "--agent-role",
                "qa",
            ]
        )
        self.assertEqual(code, 0)
        code, _ = self._run(
            [
                "task",
                "add",
                "--milestone",
                "1",
                "--title",
                "Prove it",
                "--desc",
                "Commit: test slice.\n\nVerify: tests pass.",
                "--role",
                "docs",
            ]
        )
        self.assertEqual(code, 0)
        store = Store(self.db)
        milestone = store.get_milestone(1)
        task = store.get_task(1)
        self.assertEqual((milestone.lane_group, milestone.agent_role), (2, "qa"))
        self.assertEqual(task.role, "docs")

    def test_edits_change_lane_fields(self) -> None:
        self._plan()
        self._run(
            [
                "milestone",
                "add",
                "--plan",
                "1",
                "--title",
                "Build it",
                "--desc",
                "As a user, I want the slice.",
            ]
        )
        self._run(["task", "add", "--milestone", "1", "--title", "Do it", "--desc", "Work."])
        self.assertEqual(
            self._run(["plan", "edit", "--id", "1", "--dispatch", "serial", "--max-agents", "1"])[
                0
            ],
            0,
        )
        self.assertEqual(
            self._run(
                [
                    "milestone",
                    "edit",
                    "--id",
                    "1",
                    "--lane-group",
                    "3",
                    "--agent-role",
                    "integrator",
                ]
            )[0],
            0,
        )
        self.assertEqual(self._run(["task", "edit", "--id", "1", "--role", "refactor"])[0], 0)
        store = Store(self.db)
        plan = store.get_plan(1)
        milestone = store.get_milestone(1)
        task = store.get_task(1)
        self.assertEqual((plan.dispatch_mode, plan.max_agents), ("serial", 1))
        self.assertEqual((milestone.lane_group, milestone.agent_role), (3, "integrator"))
        self.assertEqual(task.role, "refactor")

    def test_tree_and_show_render_lanes(self) -> None:
        self._plan()
        self._run(
            [
                "milestone",
                "add",
                "--plan",
                "1",
                "--title",
                "Build it",
                "--desc",
                "As a user, I want the slice.",
                "--lane-group",
                "2",
                "--agent-role",
                "qa",
            ]
        )
        self._run(
            [
                "task",
                "add",
                "--milestone",
                "1",
                "--title",
                "Prove it",
                "--desc",
                "Work.",
                "--role",
                "docs",
            ]
        )
        _, tree = self._run(["list", "--tree"])
        self.assertIn("parallel · max 3", tree)
        self.assertIn("w2 · qa", tree)
        self.assertIn("· docs", tree)
        _, show = self._run(["plan", "show", "--id", "1"])
        self.assertIn("lanes: parallel · max 3", show)
        self.assertIn("wave 2 · qa", show)


if __name__ == "__main__":
    unittest.main()
