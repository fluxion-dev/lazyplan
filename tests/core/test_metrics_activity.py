"""Daily activity buckets for the heatmap: 12 weeks ending today."""

from __future__ import annotations

import os
import tempfile
import time
import unittest
from datetime import date, timedelta

from lazyplan import metrics, services
from lazyplan.models import Status
from lazyplan.store import Store


class ActivityBucketsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = os.path.join(self.tmp.name, "t.db")
        self.store = Store(self.db)
        plan = self.store.add_plan("Plan")
        milestone = self.store.add_milestone(plan.id, "M")
        self.tasks = [self.store.add_task(milestone.id, f"T{n}") for n in range(3)]

    def _activity(self, now: float | None = None):
        return metrics.snapshot(self.store, now=now).activity

    def _done(self, index: int) -> None:
        services.set_status(self.store, "task", self.tasks[index].id, Status.DONE, actor="qa")

    def _set_event_time(self, detail: str, when: float) -> None:
        with self.store._connect() as conn:
            conn.execute("UPDATE events SET ts=? WHERE detail LIKE ?", (when, detail))

    def test_series_ends_today_and_spans_twelve_weeks(self) -> None:
        now = time.time()
        activity = self._activity(now)
        self.assertEqual(len(activity), 84)
        self.assertEqual(activity[-1].day, date.fromtimestamp(now))
        self.assertEqual(activity[0].day, date.fromtimestamp(now) - timedelta(days=83))

    def test_completions_count_on_their_local_day(self) -> None:
        self._done(0)
        self._done(1)
        activity = self._activity()
        self.assertEqual(activity[-1].done, 2)
        self.assertEqual(sum(day.done for day in activity), 2)

    def test_a_reopened_task_counts_again(self) -> None:
        self._done(0)
        services.set_status(self.store, "task", self.tasks[0].id, Status.DOING, actor="qa")
        self._done(0)
        activity = self._activity()
        self.assertEqual(activity[-1].done, 2)

    def test_the_oldest_day_is_included_and_older_is_not(self) -> None:
        self._done(0)
        self._done(1)
        oldest = time.time() - 83 * 86_400
        older = time.time() - 84 * 86_400
        self._set_event_time(f"task #{self.tasks[0].id} -> done", oldest)
        self._set_event_time(f"task #{self.tasks[1].id} -> done", older)
        activity = self._activity(time.time())
        self.assertEqual(activity[0].done, 1)
        self.assertEqual(activity[-1].done, 0)

    def test_empty_store_has_84_zero_days(self) -> None:
        empty = Store(os.path.join(self.tmp.name, "empty.db"))
        activity = metrics.snapshot(empty).activity
        self.assertEqual(len(activity), 84)
        self.assertEqual(sum(day.done for day in activity), 0)


if __name__ == "__main__":
    unittest.main()
