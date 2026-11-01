"""The bottom metrics section, its timeline card, and the responsive hide."""

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
    from lazyplan.tui.screens import PaletteScreen
    from lazyplan.tui.theme import lane_baseline_rgb
except ImportError:  # stdlib-only interpreter: no textual
    tui_mod = None  # type: ignore[assignment]
    MetricsSection = None  # type: ignore[assignment,misc]
    PaletteScreen = None  # type: ignore[assignment,misc]
    lane_baseline_rgb = None  # type: ignore[assignment]

CARD_ID = "metric-timeline"


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
        self.plan_id = plan.id
        milestone = store.add_milestone(plan.id, "Milestone title")
        task = store.add_task(milestone.id, "Task title")
        self.milestone_id = milestone.id
        self.task_id = task.id
        self.store = Store(self.db)

    async def asyncTearDown(self) -> None:
        self.tmp.cleanup()

    @staticmethod
    def _chart(card) -> str:
        return card.query_one("PlotextPlot").plt.build()

    async def test_section_renders_the_timeline_card(self) -> None:
        app = tui_mod.create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            section = app.query_one("#metrics", MetricsSection)
            self.assertTrue(section.display)
            card = section.query_one(f"#{CARD_ID}")
            self.assertIsNotNone(card.query_one("PlotextPlot"))

    async def test_section_has_no_border_title(self) -> None:
        app = tui_mod.create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            self.assertIsNone(app.query_one("#metrics", MetricsSection).border_title)

    async def test_empty_plan_shows_the_no_milestones_copy(self) -> None:
        empty = self.store.add_plan("Empty plan")
        app = tui_mod.create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.tree_controller.track(app._row_nodes[("plan", empty.id)])
            await pilot.pause(0.2)
            section = app.query_one("#metrics", MetricsSection)
            chart = self._chart(section.query_one(f"#{CARD_ID}"))
        self.assertIn("no milestones yet", chart)

    async def test_timeline_card_spans_the_section(self) -> None:
        app = tui_mod.create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            section = app.query_one("#metrics", MetricsSection)
            cards = section.query_one("#metric-cards")
            card = app.query_one(f"#{CARD_ID}")
            self.assertEqual(card.region.width, cards.region.width)
            self.assertGreater(card.region.width, 20)

    async def test_timeline_card_shows_the_project_lane(self) -> None:
        app = tui_mod.create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.tree_controller.track(app._row_nodes[("plan", self.plan_id)])
            await pilot.pause(0.2)
            chart = self._chart(app.query_one(f"#{CARD_ID}"))
        self.assertIn("Plan title", chart)
        self.assertIn("Milestone title", chart)

    async def test_section_grows_beyond_fourteen_rows(self) -> None:
        app = tui_mod.create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            self.assertGreater(app.query_one("#metrics", MetricsSection).region.height, 14)

    async def test_p117_chart_contract_is_pinned(self) -> None:
        """Guard the merged P117 shape before the modernization refactor."""
        app = tui_mod.create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            section = app.query_one("#metrics", MetricsSection)
            card = section.query_one(f"#{CARD_ID}")
            self.assertIsNotNone(card.query_one("PlotextPlot"))
            self.assertGreaterEqual(section.region.height, 14)

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

    def _other_plan(self, tasks: int = 2) -> tuple[int, int, list[int]]:
        other = self.store.add_plan("Other plan")
        milestone = self.store.add_milestone(other.id, "Other milestone")
        task_ids = [
            self.store.add_task(milestone.id, f"Other task {number}").id for number in range(tasks)
        ]
        return other.id, milestone.id, task_ids

    async def test_focus_changes_follow_the_selected_plan(self) -> None:
        other_id, _milestone_id, _task_ids = self._other_plan()
        app = tui_mod.create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            card = app.query_one(f"#{CARD_ID}")
            app.tree_controller.track(app._row_nodes[("plan", self.plan_id)])
            await pilot.pause(0.2)
            before = self._chart(card)
            app.tree_controller.track(app._row_nodes[("plan", other_id)])
            await pilot.pause(0.2)
            after = self._chart(card)
        self.assertIn("Plan title", before)
        self.assertIn("Other plan", after)
        self.assertNotIn("Plan title", after)

    async def test_milestone_and_task_rows_scope_to_their_plan(self) -> None:
        _other_id, milestone_id, task_ids = self._other_plan()
        app = tui_mod.create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            card = app.query_one(f"#{CARD_ID}")
            charts = []
            for key in (("milestone", milestone_id), ("task", task_ids[0])):
                app.tree_controller.track(app._row_nodes[key])
                await pilot.pause(0.2)
                charts.append(self._chart(card))
        for chart in charts:
            self.assertIn("Other plan", chart)
            self.assertIn("Other milestone", chart)
        self.assertNotIn("Other task 0 *", charts[0])
        self.assertIn("Other task 0", charts[1])
        self.assertNotIn("Other task 0 *", charts[1])

    async def test_task_selection_adds_sibling_task_lanes(self) -> None:
        app = tui_mod.create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.tree_controller.track(app._row_nodes[("task", self.task_id)])
            await pilot.pause(0.2)
            chart = self._chart(app.query_one(f"#{CARD_ID}"))
        self.assertIn("Task title", chart)
        self.assertNotIn("Task title *", chart)
        self.assertIn("●", chart)

    async def test_selection_emphasis_follows_the_cursor(self) -> None:
        app = tui_mod.create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            card = app.query_one(f"#{CARD_ID}")

            app.tree_controller.track(app._row_nodes[("plan", self.plan_id)])
            await pilot.pause(0.2)
            plan_chart = self._chart(card)

            app.tree_controller.track(app._row_nodes[("milestone", self.milestone_id)])
            await pilot.pause(0.2)
            milestone_chart = self._chart(card)

            app.tree_controller.track(app._row_nodes[("task", self.task_id)])
            await pilot.pause(0.2)
            task_chart = self._chart(card)

            app.tree_controller.track(app._row_nodes[("plan", self.plan_id)])
            await pilot.pause(0.2)
            cleared_chart = self._chart(card)
        self.assertIn("╍ Plan title", plan_chart)
        self.assertIn("─ Milestone title", plan_chart)
        self.assertNotIn("━ Milestone title", plan_chart)
        self.assertIn("═ Plan title", milestone_chart)
        self.assertIn("━ Milestone title", milestone_chart)
        self.assertIn("· Task title", milestone_chart)
        self.assertIn("═ Plan title", task_chart)
        self.assertIn("─ Milestone title", task_chart)
        self.assertIn("● Task title", task_chart)
        self.assertNotIn("● Task title", cleared_chart)
        self.assertIn("╍ Plan title", cleared_chart)
        for chart in (plan_chart, milestone_chart, task_chart, cleared_chart):
            self.assertNotIn(" *", chart)

    async def test_plan_draws_a_dim_baseline(self) -> None:
        app = tui_mod.create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.tree_controller.track(app._row_nodes[("plan", self.plan_id)])
            await pilot.pause(0.2)
            chart = self._chart(app.query_one(f"#{CARD_ID}"))
            baseline = lane_baseline_rgb(app, 0)
        code = f"\x1b[38;2;{baseline[0]};{baseline[1]};{baseline[2]}m"
        self.assertIn(code, chart)

    async def test_selection_emphasis_writes_nothing(self) -> None:
        events_before = len(self.store.feed(limit=10_000))
        app = tui_mod.create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            for key in (
                ("plan", self.plan_id),
                ("milestone", self.milestone_id),
                ("task", self.task_id),
            ):
                app.tree_controller.track(app._row_nodes[key])
                await pilot.pause(0.2)
        self.assertEqual(len(self.store.feed(limit=10_000)), events_before)

    async def test_external_status_change_refreshes_the_gantt(self) -> None:
        milestone_id = self.store.list_milestones(self.plan_id)[0].id
        app = tui_mod.create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.tree_controller.track(app._row_nodes[("milestone", milestone_id)])
            await pilot.pause(0.2)
            before = self._chart(app.query_one(f"#{CARD_ID}"))
            external = Store(self.db)
            services.set_status(external, "task", self.task_id, Status.DOING, actor="qa")
            app._poll()
            await pilot.pause()
            await pilot.pause()
            after = self._chart(app.query_one(f"#{CARD_ID}"))
        self.assertNotEqual(before, after)
        self.assertIn("now", after)

    async def test_now_tick_refreshes_the_timeline(self) -> None:
        with mock.patch("lazyplan.tui.controllers.metrics.NOW_TICK_SECONDS", 0.05):
            app = tui_mod.create_app(self.db)
            with mock.patch.object(MetricsSection, "refresh_snapshot") as refresh:
                async with app.run_test(size=(120, 40)) as pilot:
                    await pilot.pause()
                    refresh.reset_mock()
                    await pilot.pause(0.2)
                    self.assertGreaterEqual(refresh.call_count, 1)

    async def test_now_tick_skips_modal_screens(self) -> None:
        with mock.patch("lazyplan.tui.controllers.metrics.NOW_TICK_SECONDS", 0.05):
            app = tui_mod.create_app(self.db)
            with mock.patch.object(MetricsSection, "refresh_snapshot") as refresh:
                async with app.run_test(size=(120, 40)) as pilot:
                    await pilot.pause()
                    app.push_screen(PaletteScreen(app._palette_context()))
                    await pilot.pause()
                    refresh.reset_mock()
                    await pilot.pause(0.2)
                    self.assertEqual(refresh.call_count, 0)

    async def test_unmount_stops_the_now_tick(self) -> None:
        with mock.patch("lazyplan.tui.controllers.metrics.NOW_TICK_SECONDS", 0.05):
            app = tui_mod.create_app(self.db)
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                self.assertIsNotNone(app.metrics_controller.now_timer)
            self.assertIsNone(app.metrics_controller.now_timer)

    async def test_no_selection_falls_back_to_all_plans(self) -> None:
        self._other_plan()
        app = tui_mod.create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            card = app.query_one(f"#{CARD_ID}")
            app.selected = None
            app.metrics_controller.stop()
            app.metrics_controller.refresh()
            await pilot.pause()
            chart = self._chart(card)
        self.assertIn("Plan title", chart)
        self.assertIn("Other plan", chart)

    async def test_tree_filters_and_marks_leave_scope_alone(self) -> None:
        other_id, _milestone_id, _task_ids = self._other_plan()
        app = tui_mod.create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.tree_controller.track(app._row_nodes[("plan", other_id)])
            await pilot.pause(0.2)
            app.filter_text = "Other"
            app.marked.add(("plan", other_id))
            app.refresh_all()
            await pilot.pause()
            chart = self._chart(app.query_one(f"#{CARD_ID}"))
        self.assertIn("Other plan", chart)

    async def test_plots_fit_at_100_columns(self) -> None:
        app = tui_mod.create_app(self.db)
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            section = app.query_one("#metrics", MetricsSection)
            self.assertTrue(section.display)
            card = app.query_one(f"#{CARD_ID}")
            self.assertTrue(_within(card.region, 100, 40))
            plot = card.query_one("PlotextPlot")
            self.assertTrue(plot.display)
            self.assertTrue(_within(plot.region, 100, 40))
            self.assertLessEqual(
                plot.region.x + plot.region.width,
                card.region.x + card.region.width,
            )

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
