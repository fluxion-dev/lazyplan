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
        snapshot = metrics.snapshot(self.store)
        self.assertIsNotNone(snapshot.progress)
        self.assertEqual(snapshot.progress.total, 2)  # type: ignore[union-attr]

    def _six_milestones(self) -> list[tuple[int, int]]:
        plan = self.store.add_plan("Plan")
        created: list[tuple[int, int]] = []
        for number in range(1, 7):
            milestone = self.store.add_milestone(plan.id, f"M{number}")
            task = self.store.add_task(milestone.id, f"T{number}")
            created.append((milestone.id, task.id))
        return created

    def _set_event_time(self, detail: str, when: float) -> None:
        with self.store._connect() as conn:
            conn.execute("UPDATE events SET ts=? WHERE detail LIKE ?", (when, detail))

    def test_top_five_milestones_rank_by_recent_activity(self) -> None:
        created = self._six_milestones()
        for index, (milestone_id, task_id) in enumerate(created, start=1):
            self._set_event_time(f"M#{milestone_id} %", 1_000 + index)
            self._set_event_time(f"T#{task_id} %", 1_000 + index)
        progress = metrics.overall_progress(self.store, now=2_000)
        self.assertEqual(len(progress.milestones), 5)
        self.assertEqual(
            [item.title for item in progress.milestones],
            ["M6", "M5", "M4", "M3", "M2"],
        )

    def test_status_activity_outranks_creation_order(self) -> None:
        created = self._six_milestones()
        for index, (milestone_id, task_id) in enumerate(created, start=1):
            self._set_event_time(f"M#{milestone_id} %", 1_000 + index)
            self._set_event_time(f"T#{task_id} %", 1_000 + index)
        first_task = created[0][1]
        services.set_status(self.store, "task", first_task, Status.DONE, actor="qa")
        progress = metrics.overall_progress(self.store)
        self.assertEqual(progress.milestones[0].title, "M1")
        self.assertEqual(progress.milestones[0].done, 1)

    def test_ties_break_by_open_tasks_then_id(self) -> None:
        plan = self.store.add_plan("Plan")
        first = self.store.add_milestone(plan.id, "First")
        second = self.store.add_milestone(plan.id, "Second")
        third = self.store.add_milestone(plan.id, "Third")
        tasks = [
            self.store.add_task(first.id, "A"),
            self.store.add_task(second.id, "B"),
            self.store.add_task(second.id, "C"),
            self.store.add_task(third.id, "D"),
        ]
        for task in tasks:
            self._set_event_time(f"T#{task.id} %", 1_000)
        titles = [item.title for item in metrics.overall_progress(self.store, now=2_000).milestones]
        self.assertEqual(titles, ["Second", "First", "Third"])

    def test_eta_uses_the_fourteen_day_rate(self) -> None:
        plan = self.store.add_plan("Plan")
        milestone = self.store.add_milestone(plan.id, "M")
        tasks = [self.store.add_task(milestone.id, f"T{n}") for n in range(4)]
        for task in tasks[:2]:
            services.set_status(self.store, "task", task.id, Status.DONE, actor="qa")
        progress = metrics.overall_progress(self.store)
        self.assertAlmostEqual(progress.daily_rate, 2 / 14)
        self.assertEqual(progress.eta_days, 14)

    def test_zero_velocity_has_no_eta(self) -> None:
        self._seed()
        progress = metrics.overall_progress(self.store)
        self.assertEqual(progress.daily_rate, 0)
        self.assertIsNone(progress.eta_days)
        self.assertFalse(progress.complete)

    def test_complete_has_no_eta(self) -> None:
        _plan, _milestone = self._seed()
        for task in [task for tasks in self.store.tasks_map().values() for task in tasks]:
            services.set_status(self.store, "task", task.id, Status.DONE, actor="qa")
        progress = metrics.overall_progress(self.store)
        self.assertTrue(progress.complete)
        self.assertIsNone(progress.eta_days)

    def test_old_completions_fall_outside_the_window(self) -> None:
        plan = self.store.add_plan("Plan")
        milestone = self.store.add_milestone(plan.id, "M")
        tasks = [self.store.add_task(milestone.id, f"T{n}") for n in range(3)]
        services.set_status(self.store, "task", tasks[0].id, Status.DONE, actor="qa")
        services.set_status(self.store, "task", tasks[1].id, Status.DONE, actor="qa")
        self._set_event_time(f"task #{tasks[0].id} -> done", 0)
        self._set_event_time(f"task #{tasks[1].id} -> done", 2_000_000)
        progress = metrics.overall_progress(self.store, now=2_000_000)
        self.assertAlmostEqual(progress.daily_rate, 1 / 14)
        self.assertEqual(progress.eta_days, 14)


if __name__ == "__main__":
    unittest.main()
