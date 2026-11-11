"""The doing-row spinner keeps one frame across heartbeats and refreshes."""

from __future__ import annotations

import os
import tempfile
import unittest

from lazyplan import services
from lazyplan.core.entities import Status
from lazyplan.presentation.shared.design import SPINNER_FRAMES, status_prefix
from lazyplan.presentation.tui.controllers.spinner import SpinnerController
from lazyplan.store import Store

try:
    from lazyplan.presentation.tui import create_app
except ImportError:  # pragma: no cover - textual not installed
    create_app = None  # type: ignore[assignment]

FRAME = 3


class FakeApp:
    """Minimal host for the label cache; paint is never called."""


class TestSpinnerRows(unittest.TestCase):
    def test_a_status_change_drops_the_doing_row(self) -> None:
        controller = SpinnerController(FakeApp())  # type: ignore[arg-type]
        key = ("task", 1)
        controller.remember(key, Status.DOING, status_prefix(Status.DOING) + "Task one")
        self.assertEqual(controller.rows, {key: "Task one"})
        controller.remember(key, Status.DONE, "a finished label")
        self.assertEqual(controller.rows, {})


@unittest.skipUnless(create_app is not None, "textual not installed")
class TestSpinnerAcrossUpdates(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(os.path.join(self.tmp.name, "spinner.db"))
        self.plan = self.store.add_plan("Plan")
        self.milestone = self.store.add_milestone(self.plan.id, "Milestone")
        self.task = self.store.add_task(self.milestone.id, "Task")
        services.set_status(self.store, "task", self.task.id, Status.DOING, actor="ana")
        self.session, _ = self.store.start_session("ana", plan_id=self.plan.id)

    async def test_the_doing_row_keeps_its_frame_across_a_heartbeat(self) -> None:
        app = create_app(self.store.path)
        async with app.run_test(size=(120, 24)) as pilot:
            await pilot.pause()
            app._expanded.update({("plan", self.plan.id), ("milestone", self.milestone.id)})
            app.refresh_all()
            app.spinner_controller.stop()
            app.spinner_controller.tick = FRAME
            app.spinner_controller.paint()
            node = app._row_nodes[("task", self.task.id)]
            before = str(node.label)
            self.assertIn(SPINNER_FRAMES[FRAME], before)
            self.store.touch_session(self.session.id, phase="awaiting")
            app.tree_controller.poll_now()
            await pilot.pause()
            self.assertEqual(app.spinner_controller.tick, FRAME)
            self.assertEqual(str(node.label), before)

    async def test_the_doing_row_keeps_its_frame_across_a_structural_refresh(self) -> None:
        app = create_app(self.store.path)
        async with app.run_test(size=(120, 24)) as pilot:
            await pilot.pause()
            app._expanded.update({("plan", self.plan.id), ("milestone", self.milestone.id)})
            app.refresh_all()
            app.spinner_controller.stop()
            app.spinner_controller.tick = FRAME
            app.spinner_controller.paint()
            node = app._row_nodes[("task", self.task.id)]
            self.store.update_task(self.task.id, description="more detail", actor="ana")
            app.refresh_all()
            self.assertIs(app._row_nodes[("task", self.task.id)], node)
            self.assertEqual(app.spinner_controller.tick, FRAME)
            self.assertIn(SPINNER_FRAMES[FRAME], str(node.label))


if __name__ == "__main__":
    unittest.main()
