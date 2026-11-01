"""Timeline card: braille swimlanes and labels drawn inside the chart."""

from __future__ import annotations

import os
import tempfile
import unittest
from unittest import mock

from lazyplan import metrics, services
from lazyplan.models import Status
from lazyplan.store import Store

try:
    from lazyplan import tui as tui_mod
    from lazyplan.tui.metrics.timeline import TimelineCard
except ImportError:  # stdlib-only interpreter: no textual
    tui_mod = None  # type: ignore[assignment]
    TimelineCard = None  # type: ignore[assignment,misc]


def _at(stamp: float, action):
    with mock.patch("lazyplan.store.base.time.time", return_value=stamp):
        return action()


def _seed(store: Store) -> int:
    plan = _at(1_000, lambda: store.add_plan("Plan title"))
    first = _at(1_100, lambda: store.add_milestone(plan.id, "First milestone"))
    second = _at(1_200, lambda: store.add_milestone(plan.id, "Second milestone"))
    task = _at(1_150, lambda: store.add_task(first.id, "Task"))
    _at(1_300, lambda: services.set_status(store, "task", task.id, Status.DONE, actor="qa"))
    _at(
        1_500,
        lambda: services.set_status(store, "milestone", second.id, Status.DONE, actor="qa"),
    )
    return plan.id


def _braille(text: str) -> bool:
    return any("\u2800" <= char <= "\u28ff" for char in text)


@unittest.skipUnless(tui_mod is not None and tui_mod._TEXTUAL_OK, "textual not installed")
class TimelineCardRenderTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "t.db")
        self.store = Store(self.db)

    async def asyncTearDown(self) -> None:
        self.tmp.cleanup()

    async def test_card_renders_braille_lanes_and_inside_labels(self) -> None:
        plan_id = _seed(self.store)
        app = tui_mod.create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            card = app.query_one("#metric-timeline", TimelineCard)
            card.refresh_timeline(metrics.snapshot(self.store, now=2_000, plan_id=plan_id).timeline)
            await pilot.pause()
            plot = card.query_one("PlotextPlot")
            chart = plot.plt.build()
            self.assertTrue(plot.display)
        self.assertIn("Plan title", chart)
        self.assertIn("First milestone", chart)
        self.assertIn("Second milestone", chart)
        self.assertTrue(_braille(chart))

    async def test_card_uses_the_empty_state(self) -> None:
        app = tui_mod.create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            card = app.query_one("#metric-timeline", TimelineCard)
            card.refresh_timeline(metrics.snapshot(self.store, now=2_000).timeline)
            await pilot.pause()
            plot = card.query_one("PlotextPlot")
            chart = plot.plt.build()
            self.assertTrue(plot.display)
        self.assertIn("no plans yet", chart)

    async def test_legend_truncates_long_titles(self) -> None:
        plan = _at(1_000, lambda: self.store.add_plan("A project title that will not fit"))
        app = tui_mod.create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            card = app.query_one("#metric-timeline", TimelineCard)
            card.refresh_timeline(metrics.snapshot(self.store, now=2_000, plan_id=plan.id).timeline)
            await pilot.pause()
            chart = card.query_one("PlotextPlot").plt.build()
        self.assertIn("A project title…", chart)


if __name__ == "__main__":
    unittest.main()
