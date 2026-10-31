"""The bottom metrics section, its card slots, and the responsive hide."""

from __future__ import annotations

import os
import tempfile
import unittest
from unittest import mock

from lazyplan import services
from lazyplan.models import Status
from lazyplan.store import Store

try:
    from lazyplan import tui as tui_mod
    from lazyplan.tui.metrics import MetricsSection
except ImportError:  # stdlib-only interpreter: no textual
    tui_mod = None  # type: ignore[assignment]
    MetricsSection = None  # type: ignore[assignment,misc]

CARD_IDS = ("metric-heatmap", "metric-progress", "metric-status")
CARD_TITLES = ("Daily activity", "Project progress", "Task status")


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
        plan = store.add_plan("Plan title")
        milestone = store.add_milestone(plan.id, "Milestone title")
        task = store.add_task(milestone.id, "Task title")
        self.task_id = task.id
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

    async def test_cards_are_side_by_side(self) -> None:
        app = tui_mod.create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            regions = [app.query_one(f"#{card_id}").region for card_id in CARD_IDS]
        self.assertEqual(len({region.y for region in regions}), 1)
        self.assertLess(regions[0].x, regions[1].x)
        self.assertLess(regions[1].x, regions[2].x)
        for region in regions:
            self.assertGreater(region.width, 20)

    async def test_cards_show_data_and_the_remaining_empty_state(self) -> None:
        app = tui_mod.create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            section = app.query_one("#metrics", MetricsSection)
            activity = str(section.query_one("#metric-heatmap-empty").render())
            progress = str(section.query_one("#metric-progress-head").render())
            status_plot = section.query_one("#metric-status").query_one("PlotextPlot")
            self.assertIn("no completions yet", activity)
            self.assertIn("0% 0/1", progress)
            self.assertTrue(status_plot.display)

    async def test_section_is_twelve_rows(self) -> None:
        app = tui_mod.create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            self.assertEqual(app.query_one("#metrics", MetricsSection).region.height, 12)

    async def test_status_edit_reaches_the_host_on_refresh(self) -> None:
        app = tui_mod.create_app(self.db)
        with mock.patch.object(MetricsSection, "refresh_snapshot") as refresh:
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                services.set_status(self.store, "task", self.task_id, Status.DONE, actor="qa")
                refresh.reset_mock()
                app.refresh_all()
                await pilot.pause()
        self.assertGreaterEqual(refresh.call_count, 1)

    async def test_progress_card_updates_after_a_status_edit(self) -> None:
        app = tui_mod.create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            card = app.query_one("#metric-progress")
            before = str(card.query_one(".metric-head").render())
            services.set_status(self.store, "task", self.task_id, Status.DONE, actor="qa")
            app.refresh_all()
            await pilot.pause()
            after = str(card.query_one(".metric-head").render())
        self.assertIn("0% 0/1", before)
        self.assertIn("100% 1/1 · complete", after)

    async def test_status_card_updates_after_a_status_edit(self) -> None:
        app = tui_mod.create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            card = app.query_one("#metric-status")
            plot = card.query_one("PlotextPlot")
            before = plot.plt.build()
            services.set_status(self.store, "task", self.task_id, Status.DONE, actor="qa")
            app.refresh_all()
            await pilot.pause()
            after = plot.plt.build()
        self.assertIn("todo 100%", before)
        self.assertIn("done 100%", after)

    async def test_blocked_edit_updates_the_status_card(self) -> None:
        app = tui_mod.create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            card = app.query_one("#metric-status")
            self.store.set_blocked(self.task_id, True, "waiting", actor="qa")
            app.refresh_all()
            await pilot.pause()
            chart = card.query_one("PlotextPlot").plt.build()
        self.assertIn("blocked 100%", chart)

    async def test_heatmap_updates_after_a_done_toggle(self) -> None:
        app = tui_mod.create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            card = app.query_one("#metric-heatmap")
            empty = card.query_one(".metric-empty")
            before = str(empty.render())
            services.set_status(self.store, "task", self.task_id, Status.DONE, actor="qa")
            app.refresh_all()
            await pilot.pause()
            plot_visible = card.query_one("PlotextPlot").display
            empty_visible = empty.display
            titles = [app.query_one(f"#{card_id}") for card_id in CARD_IDS]
        self.assertIn("no completions yet", before)
        self.assertTrue(plot_visible)
        self.assertFalse(empty_visible)
        self.assertEqual(len(titles), 3)

    async def test_focus_changes_leave_progress_alone(self) -> None:
        other = self.store.add_plan("Other plan")
        app = tui_mod.create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            card = app.query_one("#metric-progress")
            before = str(card.query_one(".metric-head").render())
            app.selected = ("plan", other.id)
            app.update_preview()
            await pilot.pause()
            after = str(card.query_one(".metric-head").render())
        self.assertEqual(before, after)

    async def test_section_hides_below_100_columns(self) -> None:
        app = tui_mod.create_app(self.db)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            section = app.query_one("#metrics", MetricsSection)
            self.assertFalse(section.display)
            main = app.query_one("#main")
            self.assertTrue(_within(main.region, 80, 24))

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
