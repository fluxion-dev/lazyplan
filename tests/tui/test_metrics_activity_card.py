"""Activity card: a Plotext weekly bar chart with an empty state."""

from __future__ import annotations

import os
import tempfile
import unittest
from datetime import date, timedelta

from lazyplan import metrics
from lazyplan.store import Store

try:
    from lazyplan import tui as tui_mod
    from lazyplan.tui.metrics.activity import ActivityCard
except ImportError:  # stdlib-only interpreter: no textual
    tui_mod = None  # type: ignore[assignment]
    ActivityCard = None  # type: ignore[assignment,misc]


def _series(counts: dict[int, int] | None = None) -> tuple[metrics.DayActivity, ...]:
    start = date(2026, 8, 9)
    data = counts or {}
    return tuple(
        metrics.DayActivity(day=start + timedelta(days=offset), done=data.get(offset, 0))
        for offset in range(84)
    )


@unittest.skipUnless(tui_mod is not None and tui_mod._TEXTUAL_OK, "textual not installed")
class ActivityCardRenderTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "t.db")
        self.store = Store(self.db)

    async def asyncTearDown(self) -> None:
        self.tmp.cleanup()

    async def test_card_renders_weekly_bars(self) -> None:
        app = tui_mod.create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            card = app.query_one("#metric-heatmap", ActivityCard)
            card.refresh_activity(_series({0: 1, 40: 3, 83: 2}))
            await pilot.pause()
            plot = card.query_one("PlotextPlot")
            empty = card.query_one(".metric-empty")
            chart = plot.plt.build()
            self.assertTrue(plot.display)
            self.assertFalse(empty.display)
        self.assertIn("08-", chart)
        self.assertIn("10-", chart)

    async def test_card_uses_the_empty_state(self) -> None:
        app = tui_mod.create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            card = app.query_one("#metric-heatmap", ActivityCard)
            card.refresh_activity(_series())
            await pilot.pause()
            plot = card.query_one("PlotextPlot")
            empty = card.query_one(".metric-empty")
            text = str(empty.render())
            self.assertFalse(plot.display)
            self.assertTrue(empty.display)
        self.assertIn("no completions yet", text)


if __name__ == "__main__":
    unittest.main()
