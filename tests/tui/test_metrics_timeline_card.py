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
    from lazyplan.metrics import TimelineLane
    from lazyplan.tui.metrics.timeline import (
        TimelineCard,
        _active_segments,
        _axis_ticks,
        _lane_window,
        _legend_layout,
        _trace_glyph,
    )
except ImportError:  # stdlib-only interpreter: no textual
    tui_mod = None  # type: ignore[assignment]
    TimelineLane = None  # type: ignore[assignment,misc]
    TimelineCard = None  # type: ignore[assignment,misc]
    _active_segments = None  # type: ignore[assignment]
    _axis_ticks = None  # type: ignore[assignment]
    _lane_window = None  # type: ignore[assignment]
    _legend_layout = None  # type: ignore[assignment]
    _trace_glyph = None  # type: ignore[assignment]


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


@unittest.skipUnless(tui_mod is not None and tui_mod._TEXTUAL_OK, "textual not installed")
class TimelineCardRenderTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "t.db")
        self.store = Store(self.db)

    async def asyncTearDown(self) -> None:
        self.tmp.cleanup()

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

    async def test_inactive_lane_has_no_endpoint_markers(self) -> None:
        plan = _at(1_000, lambda: self.store.add_plan("Idle plan"))
        app = tui_mod.create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            card = app.query_one("#metric-timeline", TimelineCard)
            card.refresh_timeline(metrics.snapshot(self.store, now=2_000, plan_id=plan.id).timeline)
            await pilot.pause()
            chart = card.query_one("PlotextPlot").plt.build()
        self.assertIn("Idle plan", chart)
        self.assertNotIn("•", chart)
        self.assertNotIn("now", chart)

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

    def test_inactive_lanes_have_no_segments(self) -> None:
        idle = TimelineLane("plan", "Idle", 0, 100, ())
        active = TimelineLane("plan", "Active", 0, 100, ((10, 20), (30, 40)))

        self.assertEqual(_active_segments(idle, 0, 100, 1), [])
        self.assertEqual(_active_segments(active, 0, 100, 1), [(10, 20), (30, 40)])

    def test_lane_window_keeps_one_row_per_lane_and_spare_space_below(self) -> None:
        unit, top, bottom = _lane_window(12, 3, 3)

        self.assertEqual(unit, 1.0)
        self.assertEqual(top, 5.5)
        self.assertEqual(bottom, 6.0)

    def test_lane_window_compresses_only_when_lanes_overflow(self) -> None:
        unit, top, bottom = _lane_window(12, 10, 6)

        self.assertGreater(unit, 1.0)
        self.assertGreater(top, 10.0)
        self.assertEqual(bottom, 0.0)

    def test_trace_glyphs_distinguish_kinds(self) -> None:
        self.assertEqual(_trace_glyph("plan"), "═")
        self.assertEqual(_trace_glyph("milestone"), "─")
        self.assertEqual(_trace_glyph("task"), "·")

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
                ticks, labels = _axis_ticks(0, span, span)
                self.assertEqual(len(ticks), len(labels))
                self.assertEqual(len(set(labels)), len(labels))
                self.assertEqual(len(labels[0]), width)

    def test_legend_layout_wraps_and_trims_overflow(self) -> None:
        lanes = tuple(TimelineLane("plan", f"Lane {index}", 0, 100) for index in range(30))

        rows, hidden = _legend_layout(lanes, 40, 6)

        self.assertLessEqual(len(rows), 6)
        self.assertGreater(hidden, 0)
        self.assertTrue(rows)

    def test_legend_layout_keeps_short_lists_on_one_row(self) -> None:
        lanes = tuple(TimelineLane("plan", f"Lane {index}", 0, 100) for index in range(3))

        rows, hidden = _legend_layout(lanes, 80, 6)

        self.assertEqual(len(rows), 1)
        self.assertEqual(hidden, 0)


if __name__ == "__main__":
    unittest.main()
