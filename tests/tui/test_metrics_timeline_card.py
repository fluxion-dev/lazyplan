"""Timeline card: braille swimlanes and labels drawn inside the chart."""

from __future__ import annotations

import os
import re
import tempfile
import unittest
from unittest import mock

from lazyplan import metrics, services
from lazyplan.models import Status
from lazyplan.store import Store

try:
    from lazyplan import tui as tui_mod
    from lazyplan.metrics import TimelineLane
    from lazyplan.tui.metrics.timeline import TimelineCard
    from lazyplan.tui.metrics.timeline_layout import (
        active_segments,
        axis_ticks,
        lane_window,
        legend_entry,
        legend_layout,
        trace_glyph,
        trace_points,
    )
    from lazyplan.tui.theme import lane_baseline_rgb, lane_rgb
except ImportError:  # stdlib-only interpreter: no textual
    tui_mod = None  # type: ignore[assignment]
    TimelineLane = None  # type: ignore[assignment,misc]
    TimelineCard = None  # type: ignore[assignment,misc]
    active_segments = None  # type: ignore[assignment]
    axis_ticks = None  # type: ignore[assignment]
    lane_window = None  # type: ignore[assignment]
    legend_entry = None  # type: ignore[assignment]
    legend_layout = None  # type: ignore[assignment]
    trace_glyph = None  # type: ignore[assignment]
    trace_points = None  # type: ignore[assignment]
    lane_baseline_rgb = None  # type: ignore[assignment]
    lane_rgb = None  # type: ignore[assignment]


def _at(stamp: float, action):
    with mock.patch("lazyplan.store.base.time.time", return_value=stamp):
        return action()


def _seed(store: Store) -> int:
    plan = _at(1_000, lambda: store.add_plan("Plan title"))
    first = _at(1_100, lambda: store.add_milestone(plan.id, "First milestone"))
    second = _at(1_200, lambda: store.add_milestone(plan.id, "Second milestone"))
    task = _at(1_150, lambda: store.add_task(first.id, "Task"))
    _at(1_200, lambda: services.set_status(store, "task", task.id, Status.DOING, actor="qa"))
    _at(1_300, lambda: services.set_status(store, "task", task.id, Status.DONE, actor="qa"))
    _at(
        1_400,
        lambda: services.set_status(store, "milestone", second.id, Status.DOING, actor="qa"),
    )
    _at(
        1_500,
        lambda: services.set_status(store, "milestone", second.id, Status.DONE, actor="qa"),
    )
    return plan.id


class TimelineTraceSemanticsTest(unittest.TestCase):
    """Project and milestone traces start at doing, not at add."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "traces.db")
        self.store = Store(self.db)
        self.plan = _at(1_000, lambda: self.store.add_plan("Plan title"))
        self.first = _at(1_100, lambda: self.store.add_milestone(self.plan.id, "First"))
        self.second = _at(1_200, lambda: self.store.add_milestone(self.plan.id, "Second"))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _lanes(self) -> dict[str, object]:
        timeline = metrics.snapshot(self.store, now=2_000, plan_id=self.plan.id).timeline
        return {lane.title: lane for lane in timeline.lanes}

    def test_milestone_traces_start_at_their_own_doing_event(self) -> None:
        _at(
            1_300, lambda: services.set_status(self.store, "milestone", self.first.id, Status.DOING)
        )
        _at(1_400, lambda: services.set_status(self.store, "milestone", self.first.id, Status.DONE))
        _at(
            1_500,
            lambda: services.set_status(self.store, "milestone", self.second.id, Status.DOING),
        )
        _at(
            1_600, lambda: services.set_status(self.store, "milestone", self.second.id, Status.DONE)
        )

        lanes = self._lanes()
        first = lanes["First"]
        second = lanes["Second"]
        assert hasattr(first, "trace") and hasattr(second, "trace")
        self.assertEqual(first.trace, ((1_300, 1_400),))
        self.assertEqual(second.trace, ((1_500, 1_600),))
        self.assertEqual(first.start, 1_300)
        self.assertEqual(second.start, 1_500)
        self.assertNotEqual(first.start, second.start)

    def test_pause_splits_a_milestone_trace(self) -> None:
        _at(
            1_300, lambda: services.set_status(self.store, "milestone", self.first.id, Status.DOING)
        )
        _at(1_400, lambda: services.set_status(self.store, "milestone", self.first.id, Status.TODO))
        _at(
            1_500, lambda: services.set_status(self.store, "milestone", self.first.id, Status.DOING)
        )
        _at(1_600, lambda: services.set_status(self.store, "milestone", self.first.id, Status.DONE))

        lane = self._lanes()["First"]
        self.assertEqual(lane.trace, ((1_300, 1_400), (1_500, 1_600)))

    def test_never_doing_milestone_keeps_a_lane_without_a_trace(self) -> None:
        lane = self._lanes()["Second"]
        self.assertEqual(lane.trace, ())
        self.assertEqual(lane.start, 1_200)


@unittest.skipUnless(tui_mod is not None and tui_mod._TEXTUAL_OK, "textual not installed")
class TimelineCardRenderTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "t.db")
        self.store = Store(self.db)

    async def asyncTearDown(self) -> None:
        self.tmp.cleanup()

    @staticmethod
    def _rgb_code(rgb: tuple[int, int, int]) -> str:
        return f"\x1b[38;2;{rgb[0]};{rgb[1]};{rgb[2]}m"

    @classmethod
    def _colored_line(cls, chart: str, rgb: tuple[int, int, int], glyph: str) -> str:
        code = cls._rgb_code(rgb)
        lines = [line for line in chart.splitlines() if code in line]
        plain = [re.sub(r"\x1b\[[0-9;]*m", "", line) for line in lines]
        return max(plain, key=lambda line: line.count(glyph))

    async def test_card_renders_glyph_lanes_and_inside_labels(self) -> None:
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
        self.assertIn("•", chart)
        self.assertIn("═", chart)
        self.assertNotIn("⠒", chart)
        self.assertNotIn("now", chart)
        self.assertTrue(
            any(
                "Plan title" in line and "First milestone" in line and "Second milestone" in line
                for line in chart.splitlines()
            )
        )

    async def test_many_lanes_scroll_vertically(self) -> None:
        from textual.containers import VerticalScroll

        plan = self.store.add_plan("Big plan")
        for index in range(30):
            self.store.add_milestone(plan.id, f"Milestone {index}")
        app = tui_mod.create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.tree_controller.track(app._row_nodes[("plan", plan.id)])
            await pilot.pause(0.2)
            scroll = app.query_one("#metric-timeline-scroll", VerticalScroll)
            self.assertGreater(scroll.max_scroll_y, 0)
            scroll.scroll_end(animate=False)
            await pilot.pause()
            self.assertGreater(scroll.scroll_y, 0)

    async def test_now_marker_appears_for_open_work(self) -> None:
        plan = _at(1_000, lambda: self.store.add_plan("Open plan"))
        milestone = _at(1_100, lambda: self.store.add_milestone(plan.id, "Open milestone"))
        _at(
            1_200,
            lambda: services.set_status(
                self.store, "milestone", milestone.id, Status.DOING, actor="qa"
            ),
        )
        app = tui_mod.create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            card = app.query_one("#metric-timeline", TimelineCard)
            card.refresh_timeline(metrics.snapshot(self.store, now=2_000, plan_id=plan.id).timeline)
            await pilot.pause()
            chart = card.query_one("PlotextPlot").plt.build()
        self.assertIn("now", chart)

    async def test_selected_task_trace_renders_bold(self) -> None:
        plan = _at(1_000, lambda: self.store.add_plan("Bold plan"))
        milestone = _at(1_100, lambda: self.store.add_milestone(plan.id, "Bold milestone"))
        task = _at(1_150, lambda: self.store.add_task(milestone.id, "Bold task"))
        _at(
            1_200,
            lambda: services.set_status(self.store, "task", task.id, Status.DOING, actor="qa"),
        )
        app = tui_mod.create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.selected = ("task", task.id)
            app.metrics_controller.stop()
            card = app.query_one("#metric-timeline", TimelineCard)
            card.refresh_timeline(
                metrics.snapshot(
                    self.store,
                    now=2_000,
                    plan_id=plan.id,
                    scope_kind="task",
                    scope_id=task.id,
                ).timeline
            )
            await pilot.pause()
            chart = card.query_one("PlotextPlot").plt.build()
            baseline = lane_baseline_rgb(app, 2)
        self.assertIn("\x1b[1m", chart)
        self.assertIn("●", chart)
        self.assertIn("Bold task", chart)
        self.assertIn(self._rgb_code(baseline), chart)

    async def test_inactive_task_draws_a_full_width_baseline(self) -> None:
        plan = _at(1_000, lambda: self.store.add_plan("Idle plan"))
        milestone = _at(1_100, lambda: self.store.add_milestone(plan.id, "Idle milestone"))
        _at(1_150, lambda: self.store.add_task(milestone.id, "Idle task"))
        app = tui_mod.create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.selected = None
            app.metrics_controller.stop()
            card = app.query_one("#metric-timeline", TimelineCard)
            card.refresh_timeline(
                metrics.snapshot(
                    self.store,
                    now=2_000,
                    plan_id=plan.id,
                    scope_kind="milestone",
                    scope_id=milestone.id,
                ).timeline
            )
            await pilot.pause()
            chart = card.query_one("PlotextPlot").plt.build()
            baseline = lane_baseline_rgb(app, 2)
        code = self._rgb_code(baseline)
        self.assertIn(code, chart)
        line = next(line for line in chart.splitlines() if code in line)
        plain = re.sub(r"\x1b\[[0-9;]*m", "", line)
        self.assertGreaterEqual(plain.count("─"), 40)

    async def test_paused_project_and_milestone_span_but_task_segments(self) -> None:
        plan = _at(1_000, lambda: self.store.add_plan("Paused plan"))
        milestone = _at(1_100, lambda: self.store.add_milestone(plan.id, "Paused milestone"))
        task = _at(1_150, lambda: self.store.add_task(milestone.id, "Paused task"))
        for kind, oid in (("milestone", milestone.id), ("task", task.id)):
            _at(
                1_200,
                lambda kind=kind, oid=oid: services.set_status(
                    self.store, kind, oid, Status.DOING, actor="qa"
                ),
            )
            _at(
                1_300,
                lambda kind=kind, oid=oid: services.set_status(
                    self.store, kind, oid, Status.TODO, actor="qa"
                ),
            )
            _at(
                1_400,
                lambda kind=kind, oid=oid: services.set_status(
                    self.store, kind, oid, Status.DOING, actor="qa"
                ),
            )
        app = tui_mod.create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.selected = None
            app.metrics_controller.stop()
            card = app.query_one("#metric-timeline", TimelineCard)
            card.refresh_timeline(
                metrics.snapshot(
                    self.store,
                    now=1_500,
                    plan_id=plan.id,
                    scope_kind="task",
                    scope_id=task.id,
                ).timeline
            )
            await pilot.pause()
            chart = card.query_one("PlotextPlot").plt.build()
            plan_rgb = lane_rgb(app, 0)
            milestone_rgb = lane_rgb(app, 1)
            task_rgb = lane_rgb(app, 2)
        plan_line = self._colored_line(chart, plan_rgb, "═")
        milestone_line = self._colored_line(chart, milestone_rgb, "─")
        task_line = self._colored_line(chart, task_rgb, "·")
        self.assertGreaterEqual(plan_line.count("═"), 20)
        self.assertGreaterEqual(milestone_line.count("─"), 20)
        self.assertGreaterEqual(len(re.findall("·+", task_line)), 2)

    async def test_unselected_trace_is_not_bold(self) -> None:
        plan = _at(1_000, lambda: self.store.add_plan("Plain plan"))
        milestone = _at(1_100, lambda: self.store.add_milestone(plan.id, "Plain milestone"))
        task = _at(1_150, lambda: self.store.add_task(milestone.id, "Plain task"))
        _at(
            1_200,
            lambda: services.set_status(self.store, "task", task.id, Status.DOING, actor="qa"),
        )
        app = tui_mod.create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.selected = None
            app.metrics_controller.stop()
            card = app.query_one("#metric-timeline", TimelineCard)
            card.refresh_timeline(metrics.snapshot(self.store, now=2_000, plan_id=plan.id).timeline)
            await pilot.pause()
            chart = card.query_one("PlotextPlot").plt.build()
        self.assertNotIn("\x1b[1m", chart)
        self.assertIn("═", chart)

    async def test_inactive_open_lane_draws_no_trace(self) -> None:
        plan = _at(1_000, lambda: self.store.add_plan("Idle plan"))
        _at(1_100, lambda: self.store.add_milestone(plan.id, "Idle milestone"))
        app = tui_mod.create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.selected = None
            app.metrics_controller.stop()
            card = app.query_one("#metric-timeline", TimelineCard)
            card.refresh_timeline(metrics.snapshot(self.store, now=2_000, plan_id=plan.id).timeline)
            await pilot.pause()
            chart = card.query_one("PlotextPlot").plt.build()
        self.assertIn("Idle plan", chart)
        self.assertIn("Idle milestone", chart)
        self.assertIn("═", chart)
        self.assertNotIn("•", chart)
        self.assertIn("now", chart)

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

    async def test_scoped_plan_without_milestones_shows_its_own_empty_copy(self) -> None:
        plan = _at(1_000, lambda: self.store.add_plan("Empty plan"))
        app = tui_mod.create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            card = app.query_one("#metric-timeline", TimelineCard)
            card.refresh_timeline(metrics.snapshot(self.store, now=2_000, plan_id=plan.id).timeline)
            await pilot.pause()
            chart = card.query_one("PlotextPlot").plt.build()
        self.assertIn("no milestones yet", chart)

    async def test_legend_truncates_long_titles(self) -> None:
        plan = _at(1_000, lambda: self.store.add_plan("A project title that will not fit"))
        _at(1_100, lambda: self.store.add_milestone(plan.id, "Milestone"))
        app = tui_mod.create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            card = app.query_one("#metric-timeline", TimelineCard)
            card.refresh_timeline(metrics.snapshot(self.store, now=2_000, plan_id=plan.id).timeline)
            await pilot.pause()
            chart = card.query_one("PlotextPlot").plt.build()
        self.assertIn("A project title…", chart)

    def test_inactive_lanes_have_no_segments(self) -> None:
        idle = TimelineLane("plan", "Idle", 0, 100, ())
        active = TimelineLane("plan", "Active", 0, 100, ((10, 20), (30, 40)))

        self.assertEqual(active_segments(idle, 0, 100, 1), [])
        self.assertEqual(active_segments(active, 0, 100, 1), [(10, 20), (30, 40)])

    def testtrace_points_cover_a_segment_evenly(self) -> None:
        points = trace_points(10, 20, 0, 100, 50)

        self.assertGreaterEqual(len(points), 2)
        self.assertEqual(points[0], 10)
        self.assertEqual(points[-1], 20)
        self.assertEqual(points, sorted(points))

    def testlane_window_keeps_one_row_per_lane_and_spare_space_below(self) -> None:
        unit, top, bottom = lane_window(12, 3, 3)

        self.assertEqual(unit, 1.0)
        self.assertEqual(top, 5.5)
        self.assertEqual(bottom, 6.0)

    def testlane_window_compresses_only_when_lanes_overflow(self) -> None:
        unit, top, bottom = lane_window(12, 10, 6)

        self.assertGreater(unit, 1.0)
        self.assertGreater(top, 10.0)
        self.assertEqual(bottom, 0.0)

    def testtrace_glyphs_distinguish_kinds(self) -> None:
        self.assertEqual(trace_glyph("plan"), "═")
        self.assertEqual(trace_glyph("milestone"), "─")
        self.assertEqual(trace_glyph("task"), "·")
        self.assertEqual(trace_glyph("plan", bold=True), "╍")
        self.assertEqual(trace_glyph("milestone", bold=True), "━")
        self.assertEqual(trace_glyph("task", bold=True), "●")

    def testlegend_entry_drops_the_star_and_uses_the_bold_glyph(self) -> None:
        selected = TimelineLane("task", "Task title", 0, 100, selected=True)
        plain = TimelineLane("task", "Task title", 0, 100)

        self.assertEqual(legend_entry(selected), "● Task title")
        self.assertEqual(legend_entry(plain), "· Task title")

    def test_axis_labels_adapt_to_the_span_and_stay_unique(self) -> None:
        cases = (
            (60, 8),
            (6 * 3_600, 5),
            (3 * 86_400, 12),
            (30 * 86_400, 6),
            (365 * 86_400, 8),
        )
        for span, width in cases:
            with self.subTest(span=span):
                ticks, labels = axis_ticks(0, span, span)
                self.assertEqual(len(ticks), len(labels))
                self.assertEqual(len(set(labels)), len(labels))
                self.assertEqual(len(labels[0]), width)

    def testlegend_layout_wraps_and_trims_overflow(self) -> None:
        lanes = tuple(TimelineLane("plan", f"Lane {index}", 0, 100) for index in range(30))

        rows, hidden = legend_layout(lanes, 40, 6)

        self.assertLessEqual(len(rows), 6)
        self.assertGreater(hidden, 0)
        self.assertTrue(rows)

    def testlegend_layout_keeps_short_lists_on_one_row(self) -> None:
        lanes = tuple(TimelineLane("plan", f"Lane {index}", 0, 100) for index in range(3))

        rows, hidden = legend_layout(lanes, 80, 6)

        self.assertEqual(len(rows), 1)
        self.assertEqual(hidden, 0)


if __name__ == "__main__":
    unittest.main()
