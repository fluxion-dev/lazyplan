"""Status card: a Plotext bar chart with four labelled rows and an empty state."""

from __future__ import annotations

import os
import tempfile
import unittest

from lazyplan import metrics
from lazyplan.store import Store

try:
    from lazyplan import tui as tui_mod
    from lazyplan.tui.metrics.status import StatusCard
except ImportError:  # stdlib-only interpreter: no textual
    tui_mod = None  # type: ignore[assignment]
    StatusCard = None  # type: ignore[assignment,misc]


@unittest.skipUnless(tui_mod is not None and tui_mod._TEXTUAL_OK, "textual not installed")
class StatusCardRenderTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "t.db")
        self.store = Store(self.db)

    async def asyncTearDown(self) -> None:
        self.tmp.cleanup()

    async def test_card_renders_four_labelled_bars(self) -> None:
        app = tui_mod.create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            card = app.query_one("#metric-status", StatusCard)
            card.refresh_status(metrics.StatusBreakdown(todo=2, doing=1, done=1, blocked=1))
            await pilot.pause()
            plot = card.query_one("PlotextPlot")
            empty = card.query_one(".metric-empty")
            chart = plot.plt.build()
            self.assertTrue(plot.display)
            self.assertFalse(empty.display)
        for row in ("todo 50%", "doing 25%", "done 25%", "blocked 25%"):
            self.assertIn(row, chart)

    async def test_card_uses_the_empty_state(self) -> None:
        app = tui_mod.create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            card = app.query_one("#metric-status", StatusCard)
            card.refresh_status(metrics.StatusBreakdown())
            await pilot.pause()
            text = str(card.query_one(".metric-empty").render())
            empty_visible = card.query_one(".metric-empty").display
            plot_visible = card.query_one("PlotextPlot").display
            self.assertTrue(empty_visible)
            self.assertFalse(plot_visible)
        self.assertIn("no tasks yet", text)


if __name__ == "__main__":
    unittest.main()
