"""Pure insight computations: charts, timeline spans, and audit windows."""

from __future__ import annotations

import unittest
from datetime import date

from lazyplan.core.entities import Status, Task
from lazyplan.core.policies.insights import (
    ChartRow,
    DayActivity,
    MilestoneProgress,
    OverallProgress,
    activity_weeks,
    doing_intervals,
    milestone_bars,
    parse_since,
    status_after,
    status_bars,
    status_breakdown,
    timeline_ends,
    timeline_starts,
    work_span,
)


class TestCharts(unittest.TestCase):
    def test_activity_weeks_sums_seven_days(self) -> None:
        days = tuple(DayActivity(date(2026, 1, day), done=day) for day in range(1, 8))
        self.assertEqual(activity_weeks(days), (ChartRow("01-01", 28),))

    def test_status_bars_and_breakdown(self) -> None:
        tasks = [
            Task(id=1, milestone_id=1, title="a", status=Status.DONE),
            Task(id=2, milestone_id=1, title="b", status=Status.TODO),
        ]
        status = status_breakdown(tasks)
        self.assertEqual((status.done, status.todo, status.total), (1, 1, 2))
        self.assertEqual(status_bars(status)[0], ChartRow("todo 50%", 1))

    def test_milestone_bars(self) -> None:
        progress = OverallProgress(
            done=1,
            total=2,
            milestones=(MilestoneProgress(1, 1, "M", 1, 2),),
        )
        self.assertEqual(milestone_bars(progress), (ChartRow("M", 50),))


class TestTimeline(unittest.TestCase):
    def test_starts_and_ends(self) -> None:
        events = [
            {"ts": 10.0, "detail": "P#1 Plan"},
            {"ts": 20.0, "detail": "plan #1 -> doing"},
            {"ts": 30.0, "detail": "plan #1 -> done"},
        ]
        self.assertEqual(timeline_starts(events)[("plan", 1)], 10.0)
        self.assertEqual(timeline_ends(events)[("plan", 1)], 30.0)

    def test_pause_splits_doing_intervals(self) -> None:
        events = [
            {"ts": 10.0, "detail": "task #1 -> doing"},
            {"ts": 20.0, "detail": "task #1 -> todo"},
            {"ts": 30.0, "detail": "task #1 -> doing"},
        ]
        intervals = doing_intervals("task", 1, Status.DOING, events, 0.0, 40.0)
        self.assertEqual(intervals, ((10.0, 20.0), (30.0, 40.0)))
        self.assertEqual(work_span(intervals, 5.0, None, 40.0), (10.0, 40.0))


class TestAuditWindows(unittest.TestCase):
    def test_parse_since_empty(self) -> None:
        self.assertIsNone(parse_since(""))

    def test_parse_since_iso(self) -> None:
        self.assertIsNotNone(parse_since("2026-01-01"))

    def test_status_after(self) -> None:
        times = {1: [(5.0, Status.TODO), (10.0, Status.DOING)]}
        self.assertEqual(status_after(times, 1, 8), 10.0)
        self.assertIsNone(status_after(times, 1, 11))


if __name__ == "__main__":
    unittest.main()
