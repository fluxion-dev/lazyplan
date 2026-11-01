"""Timeline lanes: wall-clock starts and finishes for plans and milestones."""

from __future__ import annotations

import os
import tempfile
import unittest
from unittest import mock

from lazyplan import metrics, services
from lazyplan.models import Status
from lazyplan.store import Store


class TimelineSnapshotTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = os.path.join(self.tmp.name, "t.db")
        self.store = Store(self.db)

    def _at(self, stamp: float, action):
        with mock.patch("lazyplan.store.base.time.time", return_value=stamp):
            return action()

    def test_scoped_timeline_covers_the_project_and_its_milestones(self) -> None:
        plan = self._at(1_000, lambda: self.store.add_plan("Plan"))
        first = self._at(1_100, lambda: self.store.add_milestone(plan.id, "First"))
        second = self._at(1_200, lambda: self.store.add_milestone(plan.id, "Second"))
        task = self._at(1_150, lambda: self.store.add_task(first.id, "Task"))
        self._at(
            1_300,
            lambda: services.set_status(self.store, "task", task.id, Status.DONE, actor="qa"),
        )
        self._at(
            1_500,
            lambda: services.set_status(
                self.store, "milestone", second.id, Status.DONE, actor="qa"
            ),
        )

        snap = metrics.snapshot(self.store, now=2_000, plan_id=plan.id)

        assert snap.timeline is not None
        self.assertEqual(
            [lane.kind for lane in snap.timeline.lanes], ["plan", "milestone", "milestone"]
        )
        self.assertEqual(
            [(lane.title, lane.start, lane.end) for lane in snap.timeline.lanes],
            [
                ("Plan", 1_000, 1_500),
                ("First", 1_100, 1_300),
                ("Second", 1_200, 1_500),
            ],
        )
        self.assertEqual([lane.active for lane in snap.timeline.lanes], [(), (), ()])
        self.assertEqual((snap.timeline.start, snap.timeline.end), (1_000, 1_500))

    def test_active_intervals_pause_and_resume(self) -> None:
        plan = self._at(1_000, lambda: self.store.add_plan("Plan"))
        milestone = self._at(1_100, lambda: self.store.add_milestone(plan.id, "Milestone"))
        self._at(
            1_200,
            lambda: services.set_status(
                self.store, "milestone", milestone.id, Status.DOING, actor="qa"
            ),
        )
        snap = metrics.snapshot(self.store, now=1_300, plan_id=plan.id)
        assert snap.timeline is not None
        self.assertEqual([lane.active for lane in snap.timeline.lanes], [((1_200, 1_300),)] * 2)

        self._at(
            1_400,
            lambda: services.set_status(
                self.store, "milestone", milestone.id, Status.TODO, actor="qa"
            ),
        )
        snap = metrics.snapshot(self.store, now=1_500, plan_id=plan.id)
        assert snap.timeline is not None
        self.assertEqual([lane.active for lane in snap.timeline.lanes], [((1_200, 1_400),)] * 2)

        self._at(
            1_600,
            lambda: services.set_status(
                self.store, "milestone", milestone.id, Status.DOING, actor="qa"
            ),
        )
        snap = metrics.snapshot(self.store, now=1_700, plan_id=plan.id)
        assert snap.timeline is not None
        self.assertEqual(
            [lane.active for lane in snap.timeline.lanes],
            [((1_200, 1_400), (1_600, 1_700))] * 2,
        )

        self._at(
            1_800,
            lambda: services.set_status(
                self.store, "milestone", milestone.id, Status.DONE, actor="qa"
            ),
        )
        snap = metrics.snapshot(self.store, now=1_900, plan_id=plan.id)
        assert snap.timeline is not None
        self.assertEqual(
            [lane.active for lane in snap.timeline.lanes],
            [((1_200, 1_400), (1_600, 1_800))] * 2,
        )

    def test_unstarted_and_direct_done_lanes_have_no_active_interval(self) -> None:
        plan = self._at(1_000, lambda: self.store.add_plan("Plan"))
        milestone = self._at(1_100, lambda: self.store.add_milestone(plan.id, "Milestone"))
        task = self._at(1_150, lambda: self.store.add_task(milestone.id, "Task"))
        self._at(
            1_200,
            lambda: services.set_status(self.store, "task", task.id, Status.DONE, actor="qa"),
        )

        snap = metrics.snapshot(self.store, now=2_000, plan_id=plan.id)

        assert snap.timeline is not None
        self.assertEqual([lane.active for lane in snap.timeline.lanes], [(), ()])

    def test_doing_status_without_a_status_event_falls_back_to_the_start(self) -> None:
        plan = self._at(1_000, lambda: self.store.add_plan("Plan"))
        milestone = self._at(1_100, lambda: self.store.add_milestone(plan.id, "Milestone"))
        self.store.set_status_raw("milestone", milestone.id, Status.DOING)

        snap = metrics.snapshot(self.store, now=2_000, plan_id=plan.id)

        assert snap.timeline is not None
        self.assertEqual(snap.timeline.lanes[1].active, ((1_100, 2_000),))

    def test_task_doing_intervals_are_parsed(self) -> None:
        plan = self._at(1_000, lambda: self.store.add_plan("Plan"))
        milestone = self._at(1_100, lambda: self.store.add_milestone(plan.id, "Milestone"))
        task = self._at(1_150, lambda: self.store.add_task(milestone.id, "Task"))
        self._at(
            1_200,
            lambda: services.set_status(self.store, "task", task.id, Status.DOING, actor="qa"),
        )
        self._at(
            1_400,
            lambda: services.set_status(self.store, "task", task.id, Status.DONE, actor="qa"),
        )

        events = metrics._events(self.store)
        intervals = metrics._doing_intervals("task", task.id, Status.DONE, events, 1_150, 2_000)

        self.assertEqual(intervals, ((1_200, 1_400),))

    def test_open_work_ends_at_now(self) -> None:
        plan = self._at(1_000, lambda: self.store.add_plan("Plan"))
        self._at(1_100, lambda: self.store.add_milestone(plan.id, "Open"))

        snap = metrics.snapshot(self.store, now=2_000, plan_id=plan.id)

        assert snap.timeline is not None
        self.assertEqual([lane.end for lane in snap.timeline.lanes], [2_000, 2_000])

    def test_unscoped_timeline_lists_every_plan(self) -> None:
        self._at(1_000, lambda: self.store.add_plan("First plan"))
        self._at(2_000, lambda: self.store.add_plan("Second plan"))

        snap = metrics.snapshot(self.store, now=3_000)

        assert snap.timeline is not None
        self.assertEqual(
            [(lane.title, lane.start, lane.end) for lane in snap.timeline.lanes],
            [("First plan", 1_000, 3_000), ("Second plan", 2_000, 3_000)],
        )

    def test_unknown_plan_has_no_lanes(self) -> None:
        self.store.add_plan("Plan")

        snap = metrics.snapshot(self.store, now=2_000, plan_id=999)

        assert snap.timeline is not None
        self.assertEqual(snap.timeline.lanes, ())


if __name__ == "__main__":
    unittest.main()
