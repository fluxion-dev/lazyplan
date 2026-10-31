"""Heatmap card rendering: week grid, shades, legend, and empty state."""

from __future__ import annotations

import os
import tempfile
import unittest
from datetime import date, timedelta

from lazyplan import metrics
from lazyplan.store import Store

try:
    from lazyplan import tui as tui_mod
    from lazyplan.tui.metrics.heatmap import HeatmapCard, render_heatmap
except ImportError:  # stdlib-only interpreter: no textual
    tui_mod = None  # type: ignore[assignment]
    HeatmapCard = None  # type: ignore[assignment,misc]
    render_heatmap = None  # type: ignore[assignment]


def _series(counts: dict[int, int] | None = None) -> tuple[metrics.DayActivity, ...]:
    start = date(2026, 8, 9)
    data = counts or {}
    return tuple(
        metrics.DayActivity(day=start + timedelta(days=offset), done=data.get(offset, 0))
        for offset in range(84)
    )


@unittest.skipUnless(tui_mod is not None and tui_mod._TEXTUAL_OK, "textual not installed")
class HeatmapCardRenderTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "t.db")
        self.store = Store(self.db)

    async def asyncTearDown(self) -> None:
        self.tmp.cleanup()

    async def test_card_renders_the_grid(self) -> None:
        app = tui_mod.create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            card = app.query_one("#metric-heatmap", HeatmapCard)
            card.refresh_activity(_series({0: 1, 40: 3, 83: 2}))
            body = str(card.query_one(".metric-body").render())
        self.assertEqual(len(body.splitlines()), 8)
        self.assertIn("less", body)
        self.assertIn("more", body)
        self.assertIn("08-09", body)
        self.assertIn("10-31", body)

    async def test_card_uses_the_empty_state(self) -> None:
        app = tui_mod.create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            card = app.query_one("#metric-heatmap", HeatmapCard)
            card.refresh_activity(_series())
            body = str(card.query_one(".metric-body").render())
        self.assertIn("no completions yet", body)


@unittest.skipUnless(tui_mod is not None and tui_mod._TEXTUAL_OK, "textual not installed")
class HeatmapBodyTest(unittest.TestCase):
    def test_grid_has_twelve_columns_and_seven_rows(self) -> None:
        body = render_heatmap(_series({83: 1}))
        grid = body.splitlines()[:7]
        for line in grid:
            self.assertEqual(line.count("█"), 12)

    def test_empty_series_renders_nothing(self) -> None:
        self.assertEqual(render_heatmap(_series()), "")


if __name__ == "__main__":
    unittest.main()
