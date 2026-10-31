"""Status card rendering: four rows, shares, bars, and the empty state."""

from __future__ import annotations

import os
import tempfile
import unittest

from lazyplan import metrics
from lazyplan.store import Store

try:
    from lazyplan import tui as tui_mod
    from lazyplan.tui.metrics.status import StatusCard, render_status
except ImportError:  # stdlib-only interpreter: no textual
    tui_mod = None  # type: ignore[assignment]
    StatusCard = None  # type: ignore[assignment,misc]
    render_status = None  # type: ignore[assignment]


@unittest.skipUnless(tui_mod is not None and tui_mod._TEXTUAL_OK, "textual not installed")
class StatusCardRenderTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "t.db")
        self.store = Store(self.db)

    async def asyncTearDown(self) -> None:
        self.tmp.cleanup()

    async def test_card_renders_all_four_rows(self) -> None:
        app = tui_mod.create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            card = app.query_one("#metric-status", StatusCard)
            card.refresh_status(metrics.StatusBreakdown(todo=2, doing=1, done=1, blocked=1))
            body = str(card.query_one(".metric-body").render())
        for row in ("todo", "doing", "done", "blocked"):
            self.assertIn(row, body)
        self.assertIn("50%", body)
        self.assertIn("25%", body)

    async def test_card_uses_the_empty_state(self) -> None:
        app = tui_mod.create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            card = app.query_one("#metric-status", StatusCard)
            card.refresh_status(metrics.StatusBreakdown())
            body = str(card.query_one(".metric-body").render())
        self.assertIn("no tasks yet", body)


@unittest.skipUnless(tui_mod is not None and tui_mod._TEXTUAL_OK, "textual not installed")
class StatusBodyTest(unittest.TestCase):
    def test_blocked_is_an_overlay_row(self) -> None:
        body = render_status(metrics.StatusBreakdown(todo=2, doing=1, done=1, blocked=1))
        self.assertEqual(body.count("\n"), 3)
        self.assertIn("blocked", body)
        self.assertIn("25%", body)

    def test_bars_scale_to_the_largest_row(self) -> None:
        body = render_status(metrics.StatusBreakdown(todo=0, doing=0, done=8, blocked=0))
        self.assertEqual(body.count("█"), 10)
        self.assertEqual(body.count("░"), 30)

    def test_no_tasks_renders_nothing(self) -> None:
        self.assertEqual(render_status(metrics.StatusBreakdown()), "")


if __name__ == "__main__":
    unittest.main()
