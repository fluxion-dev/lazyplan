"""Progress card: headline plus a Plotext milestone bar chart."""

from __future__ import annotations

import os
import tempfile
import unittest

from lazyplan import metrics, services
from lazyplan.models import Status
from lazyplan.store import Store

try:
    from lazyplan import tui as tui_mod
    from lazyplan.tui.metrics.progress import ProgressCard, _headline
except ImportError:  # stdlib-only interpreter: no textual
    tui_mod = None  # type: ignore[assignment]
    ProgressCard = None  # type: ignore[assignment,misc]
    _headline = None  # type: ignore[assignment]


def _seed(store: Store) -> None:
    plan = store.add_plan("Plan")
    first = store.add_milestone(plan.id, "First milestone")
    second = store.add_milestone(plan.id, "Second milestone")
    done = store.add_task(first.id, "Done task")
    store.add_task(first.id, "Open task")
    store.add_task(second.id, "Other task")
    services.set_status(store, "task", done.id, Status.DONE, actor="qa")


@unittest.skipUnless(tui_mod is not None and tui_mod._TEXTUAL_OK, "textual not installed")
class ProgressCardRenderTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "t.db")
        self.store = Store(self.db)

    async def asyncTearDown(self) -> None:
        self.tmp.cleanup()

    async def test_card_renders_headline_and_milestone_bars(self) -> None:
        _seed(self.store)
        app = tui_mod.create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            card = app.query_one("#metric-progress", ProgressCard)
            card.refresh_progress(metrics.snapshot(self.store).progress)
            await pilot.pause()
            head = str(card.query_one(".metric-head").render())
            plot = card.query_one("PlotextPlot")
            empty = card.query_one(".metric-empty")
            chart = plot.plt.build()
            self.assertTrue(plot.display)
            self.assertFalse(empty.display)
        self.assertIn("33% 1/3", head)
        self.assertIn("ETA", head)
        self.assertIn("First milestone", chart)
        self.assertIn("Second milestone", chart)

    async def test_card_uses_the_empty_state(self) -> None:
        app = tui_mod.create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            card = app.query_one("#metric-progress", ProgressCard)
            card.refresh_progress(metrics.snapshot(self.store).progress)
            await pilot.pause()
            text = str(card.query_one(".metric-empty").render())
            empty_visible = card.query_one(".metric-empty").display
            head_visible = card.query_one(".metric-head").display
            plot_visible = card.query_one("PlotextPlot").display
            self.assertTrue(empty_visible)
            self.assertFalse(head_visible)
            self.assertFalse(plot_visible)
        self.assertIn("no plans yet", text)

    async def test_complete_headline_skips_the_eta(self) -> None:
        _seed(self.store)
        for tasks in self.store.tasks_map().values():
            for task in tasks:
                services.set_status(self.store, "task", task.id, Status.DONE, actor="qa")
        progress = metrics.snapshot(self.store).progress
        assert progress is not None
        headline = _headline(progress)
        self.assertIn("100% 3/3 · complete", headline)
        self.assertNotIn("ETA", headline)


if __name__ == "__main__":
    unittest.main()
