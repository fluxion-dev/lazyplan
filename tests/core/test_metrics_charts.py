"""Chart-ready rows: weekly activity, milestone percentages, status shares."""

from __future__ import annotations

import unittest
from datetime import date, timedelta

from lazyplan import metrics


def _activity(counts: dict[int, int] | None = None) -> tuple[metrics.DayActivity, ...]:
    start = date(2026, 8, 9)
    data = counts or {}
    return tuple(
        metrics.DayActivity(day=start + timedelta(days=offset), done=data.get(offset, 0))
        for offset in range(84)
    )


class ChartRowsTest(unittest.TestCase):
    def test_activity_sums_into_twelve_weeks(self) -> None:
        rows = metrics.activity_weeks(_activity({0: 1, 6: 2, 83: 3}))
        self.assertEqual(len(rows), 12)
        self.assertEqual(rows[0].label, "08-09")
        self.assertEqual(rows[0].value, 3)
        self.assertEqual(rows[-1].value, 3)

    def test_activity_accepts_a_partial_series(self) -> None:
        rows = metrics.activity_weeks(_activity()[:10])
        self.assertEqual(len(rows), 2)
        self.assertEqual(sum(row.value for row in rows), 0)

    def test_milestone_rows_use_percentages(self) -> None:
        item = metrics.MilestoneProgress(1, 1, "Shipping", done=1, total=4)
        progress = metrics.OverallProgress(done=1, total=4, milestones=(item,))
        self.assertEqual(metrics.milestone_bars(progress), (metrics.ChartRow("Shipping", 25),))

    def test_status_rows_carry_counts_and_shares(self) -> None:
        rows = metrics.status_bars(metrics.StatusBreakdown(todo=2, doing=1, done=1, blocked=1))
        self.assertEqual(
            rows,
            (
                metrics.ChartRow("todo 50%", 2),
                metrics.ChartRow("doing 25%", 1),
                metrics.ChartRow("done 25%", 1),
                metrics.ChartRow("blocked 25%", 1),
            ),
        )

    def test_empty_status_rows_are_zero(self) -> None:
        rows = metrics.status_bars(metrics.StatusBreakdown())
        self.assertEqual([row.value for row in rows], [0, 0, 0, 0])


if __name__ == "__main__":
    unittest.main()
