"""Overall progress aggregation: completion counts and elapsed time."""

from __future__ import annotations

import os
import tempfile
import unittest

from lazyplan import metrics, services
from lazyplan.models import Status
from lazyplan.store import Store


class ProgressAggregationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = os.path.join(self.tmp.name, "t.db")
        self.store = Store(self.db)

    def _seed(self) -> tuple[int, int]:
        plan = self.store.add_plan("Plan")
        milestone = self.store.add_milestone(plan.id, "Milestone")
        self.store.add_task(milestone.id, "First")
        self.store.add_task(milestone.id, "Second")
        return plan.id, milestone.id

    def _earliest_add(self) -> float:
        return min(metrics._add_times(metrics._events(self.store)))

    def test_counts_tasks_across_every_plan(self) -> None:
        self._seed()
        second_plan = self.store.add_plan("Second plan")
        milestone = self.store.add_milestone(second_plan.id, "Other")
        self.store.add_task(milestone.id, "Third")
        progress = metrics.overall_progress(self.store)
        self.assertEqual(progress.total, 3)
        self.assertEqual(progress.done, 0)
        self.assertEqual(progress.percent, 0)

    def test_done_count_and_percentage(self) -> None:
        self._seed()
        all_tasks = [task for tasks in self.store.tasks_map().values() for task in tasks]
        services.set_status(self.store, "task", all_tasks[0].id, Status.DONE, actor="qa")
        progress = metrics.overall_progress(self.store)
        self.assertEqual((progress.done, progress.total), (1, 2))
        self.assertEqual(progress.percent, 50)

    def test_elapsed_uses_the_earliest_add_event(self) -> None:
        self._seed()
        start = self._earliest_add()
        progress = metrics.overall_progress(self.store, now=start + 3_600)
        self.assertEqual(progress.elapsed_seconds, 3_600)

    def test_no_events_means_no_elapsed_time(self) -> None:
        self.assertEqual(metrics.overall_progress(self.store).elapsed_seconds, None)

    def test_snapshot_carries_progress(self) -> None:
        self._seed()
        progress = metrics.snapshot(self.store)
        self.assertIsNotNone(progress.progress)
        self.assertEqual(progress.progress.total, 2)  # type: ignore[union-attr]


if __name__ == "__main__":
    unittest.main()
