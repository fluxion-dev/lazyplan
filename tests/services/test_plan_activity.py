"""Plan activity ordering uses one bounded read and keeps parity."""

from __future__ import annotations

import os
import tempfile
import unittest

from lazyplan import services
from lazyplan.store import Store


class PlanActivityTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "activity.db")
        store = Store(self.db)
        self.first = store.add_plan("First")
        self.second = store.add_plan("Second")
        milestone = store.add_milestone(self.first.id, "Slice")
        task = store.add_task(milestone.id, "Task")
        criterion = store.add_criteria("task", task.id, "Done")
        self.milestone_id = milestone.id
        self.task_id = task.id
        self.criterion_id = criterion.id
        self.store = Store(self.db)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_latest_event_per_plan_across_detail_shapes(self) -> None:
        self.store.log("a", "task", "status", f"T#{self.task_id} -> doing")
        self.store.log("a", "milestone", "status", f"M#{self.milestone_id} -> doing")
        self.store.log("a", "criteria", "check", f"criteria #{self.criterion_id}")
        self.store.log("a", "plan", "status", f"plan #{self.first.id} -> doing")
        activity = self.store.plan_activity_map()
        self.assertIn(self.first.id, activity)
        self.assertIn(self.second.id, activity)

    def test_tree_ordering_is_recent_first(self) -> None:
        self.store.log("a", "plan", "status", f"plan #{self.first.id} -> doing")
        self.store.log("a", "plan", "status", f"plan #{self.second.id} -> doing")
        plans = [plan.id for plan, _ in services.tree(self.store, archived="show")]
        self.assertEqual(plans[0], self.second.id)

    def test_bounded_window_only_sees_recent_events(self) -> None:
        self.store.log("a", "plan", "status", f"plan #{self.first.id} -> doing")
        self.store.log("a", "plan", "status", f"plan #{self.second.id} -> doing")
        activity = self.store.plan_activity_map(limit_events=1)
        self.assertEqual(set(activity), {self.second.id})

    def test_map_matches_the_reference_parser(self) -> None:
        self.store.log("a", "task", "status", f"T#{self.task_id} -> doing")
        self.store.log("a", "milestone", "edit", f"milestone #{self.milestone_id} title")
        self.store.log("a", "criteria", "check", f"criteria #{self.criterion_id}")
        expected = services._plan_activity(
            self.store.milestones_map(),
            self.store.tasks_map(),
            self.store.criteria_map(),
            self.store.feed(limit=1000),
        )
        self.assertEqual(self.store.plan_activity_map(), expected)


if __name__ == "__main__":
    unittest.main()
