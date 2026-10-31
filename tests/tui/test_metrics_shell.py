"""The bottom metrics section, its card slots, and the responsive hide."""

from __future__ import annotations

import os
import tempfile
import unittest
from unittest import mock

from lazyplan.store import Store

try:
    from lazyplan import tui as tui_mod
    from lazyplan.tui.metrics import MetricsSection
except ImportError:  # stdlib-only interpreter: no textual
    tui_mod = None  # type: ignore[assignment]
    MetricsSection = None  # type: ignore[assignment,misc]

CARD_IDS = ("metric-heatmap", "metric-progress", "metric-status")
CARD_TITLES = ("Activity", "Progress", "Status")


def _within(region, width: int, height: int) -> bool:
    return (
        region.x >= 0
        and region.y >= 0
        and region.x + region.width <= width
        and region.y + region.height <= height
    )


@unittest.skipUnless(tui_mod is not None and tui_mod._TEXTUAL_OK, "textual not installed")
class MetricsShellTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "t.db")
        store = Store(self.db)
        store.add_plan("Plan title")
        self.store = Store(self.db)

    async def asyncTearDown(self) -> None:
        self.tmp.cleanup()

    async def test_section_renders_three_titled_cards(self) -> None:
        app = tui_mod.create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            section = app.query_one("#metrics", MetricsSection)
            self.assertTrue(section.display)
            for card_id, title in zip(CARD_IDS, CARD_TITLES, strict=True):
                card = section.query_one(f"#{card_id}")
                self.assertIn(title, str(card.query_one(".metric-title").content))

    async def test_cards_start_with_empty_states(self) -> None:
        app = tui_mod.create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            section = app.query_one("#metrics", MetricsSection)
            bodies = [str(card.query_one(".metric-body").render()) for card in section.children]
            self.assertIn("no completions yet", bodies[0])
            self.assertIn("no plans yet", bodies[1])
            self.assertIn("no tasks yet", bodies[2])

    async def test_refresh_pushes_a_snapshot_without_writing(self) -> None:
        app = tui_mod.create_app(self.db)
        events_before = len(self.store.feed(limit=10_000))
        with mock.patch.object(MetricsSection, "refresh_snapshot") as refresh:
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                app.refresh_all()
                await pilot.pause()
        self.assertGreaterEqual(refresh.call_count, 1)
        self.assertEqual(len(self.store.feed(limit=10_000)), events_before)


if __name__ == "__main__":
    unittest.main()
