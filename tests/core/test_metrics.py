"""Metrics snapshot contract: frozen values, percentages, and the shell state."""

from __future__ import annotations

import os
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from datetime import date

from lazyplan import metrics
from lazyplan.store import Store


class SnapshotContractTest(unittest.TestCase):
    """The dashboard contract is immutable and safe to render before panels."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = os.path.join(self.tmp.name, "t.db")
        self.store = Store(self.db)

    def test_default_snapshot_has_no_sections(self) -> None:
        snap = metrics.MetricsSnapshot()
        self.assertEqual(snap.activity, ())
        self.assertIsNone(snap.progress)
        self.assertIsNone(snap.status)

    def test_snapshot_carries_progress_for_any_store(self) -> None:
        self.store.add_plan("P")
        snap = metrics.snapshot(self.store, now=1_000)
        self.assertIsNotNone(snap.progress)
        self.assertEqual(snap.progress.total, 0)  # type: ignore[union-attr]

    def test_values_are_frozen(self) -> None:
        snap = metrics.MetricsSnapshot()
        with self.assertRaises(FrozenInstanceError):
            snap.status = metrics.StatusBreakdown()  # type: ignore[misc]

    def test_progress_percent(self) -> None:
        self.assertEqual(metrics.OverallProgress(done=3, total=4).percent, 75)
        self.assertEqual(metrics.OverallProgress().percent, 0)

    def test_milestone_percent(self) -> None:
        item = metrics.MilestoneProgress(1, 2, "M", done=1, total=3)
        self.assertEqual(item.percent, 33)
        self.assertEqual(metrics.MilestoneProgress(1, 2, "M", 0, 0).percent, 0)

    def test_status_share(self) -> None:
        status = metrics.StatusBreakdown(todo=2, doing=1, done=1, blocked=1)
        self.assertEqual(status.total, 4)
        self.assertEqual(status.share(2), 50)
        self.assertEqual(status.share(1), 25)
        self.assertEqual(metrics.StatusBreakdown().share(1), 0)

    def test_day_activity_keeps_a_local_date(self) -> None:
        item = metrics.DayActivity(date(2026, 10, 31), done=2)
        self.assertEqual(item.day.isoformat(), "2026-10-31")
        self.assertEqual(item.done, 2)


if __name__ == "__main__":
    unittest.main()
