"""Controller seams: pure tree math, git cache, and update chip state."""

from __future__ import annotations

import os
import tempfile
import time
import unittest
from unittest import mock

from lazyplan import services
from lazyplan.models import Milestone, Plan, Status, Task
from lazyplan.store import Store

try:
    from lazyplan import tui as tui_mod
    from lazyplan.tui.controllers.git_state import GitStateController
    from lazyplan.tui.controllers.tree import TreeController
except ImportError:  # pragma: no cover - stdlib-only interpreter
    tui_mod = None  # type: ignore[assignment]


@unittest.skipUnless(tui_mod is not None and tui_mod._TEXTUAL_OK, "textual not installed")
class ControllerTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "t.db")
        store = Store(self.db)
        plan = store.add_plan("Plan")
        milestone = store.add_milestone(plan.id, "Milestone")
        task = store.add_task(milestone.id, "Task")
        services.set_status(store, "task", task.id, Status.DONE, actor="qa")
        self.store = Store(self.db)
        self.task_id = task.id
        self.app = tui_mod.create_app(self.db)

    async def asyncTearDown(self) -> None:
        self.tmp.cleanup()

    def test_progress_map_counts_done_and_total(self) -> None:
        plan = Plan(id=1, name="P")
        milestone = Milestone(id=2, plan_id=1, title="M")
        done = Task(id=3, milestone_id=2, title="Done", status=Status.DONE)
        todo = Task(id=4, milestone_id=2, title="Todo")
        progress = TreeController.progress_map([(plan, [(milestone, [done, todo])])])
        self.assertEqual(progress[("plan", 1)], (1, 2))
        self.assertEqual(progress[("milestone", 2)], (1, 2))

    async def test_git_cache_returns_a_fresh_value_without_a_worker(self) -> None:
        controller = GitStateController(self.app)
        state = controller.empty()
        state["branch"] = "main"
        controller.cache["/repo"] = (time.time(), state)
        self.assertEqual(controller.state("/repo")["branch"], "main")

    async def test_update_chip_toasts_once_and_clears(self) -> None:
        async with self.app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            controller = self.app.update_controller
            with mock.patch.object(self.app, "notify") as toast:
                controller.announce("update v9.9.9 available", "9.9.9")
                controller.announce("update v9.9.9 available", "9.9.9")
            self.assertEqual(toast.call_count, 1)
            self.assertEqual(controller.latest, "9.9.9")
            controller.clear()
            self.assertIsNone(controller.notice)
            self.assertEqual(controller.latest, "")

    async def test_tree_rows_are_rich_text(self) -> None:
        from rich.text import Text

        async with self.app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            label = self.app._row_nodes[("task", self.task_id)].label
            self.assertIsInstance(label, Text)
            self.assertIn("Task", str(label))

    async def test_refresh_keeps_the_selected_row(self) -> None:
        async with self.app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            self.app.selected = ("task", self.task_id)
            self.app.refresh_all()
            await pilot.pause()
            self.assertEqual(self.app.selected, ("task", self.task_id))


if __name__ == "__main__":
    unittest.main()
