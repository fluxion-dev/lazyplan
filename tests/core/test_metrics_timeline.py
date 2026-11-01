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
        self.assertEqual(
            [lane.trace for lane in snap.timeline.lanes],
            [((1_000, 1_500),), ((1_100, 1_300),), ((1_200, 1_500),)],
        )
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

    def test_paused_project_and_milestone_traces_stay_continuous(self) -> None:
        plan = self._at(1_000, lambda: self.store.add_plan("Plan"))
        milestone = self._at(1_100, lambda: self.store.add_milestone(plan.id, "Milestone"))
        self._at(
            1_200,
            lambda: services.set_status(
                self.store, "milestone", milestone.id, Status.DOING, actor="qa"
            ),
        )
        self._at(
            1_300,
            lambda: services.set_status(
                self.store, "milestone", milestone.id, Status.TODO, actor="qa"
            ),
        )
        self._at(
            1_400,
            lambda: services.set_status(
                self.store, "milestone", milestone.id, Status.DOING, actor="qa"
            ),
        )

        snap = metrics.snapshot(self.store, now=1_500, plan_id=plan.id)

        assert snap.timeline is not None
        plan_lane, milestone_lane = snap.timeline.lanes
        self.assertEqual(plan_lane.active, ((1_200, 1_300), (1_400, 1_500)))
        self.assertEqual(milestone_lane.active, ((1_200, 1_300), (1_400, 1_500)))
        self.assertEqual(plan_lane.trace, ((1_000, 1_500),))
        self.assertEqual(milestone_lane.trace, ((1_100, 1_500),))

    def test_task_trace_keeps_doing_segments(self) -> None:
        plan = self._at(1_000, lambda: self.store.add_plan("Plan"))
        milestone = self._at(1_100, lambda: self.store.add_milestone(plan.id, "Milestone"))
        task = self._at(1_150, lambda: self.store.add_task(milestone.id, "Task"))
        self._at(
            1_200,
            lambda: services.set_status(self.store, "task", task.id, Status.DOING, actor="qa"),
        )
        self._at(
            1_300,
            lambda: services.set_status(self.store, "task", task.id, Status.TODO, actor="qa"),
        )
        self._at(
            1_400,
            lambda: services.set_status(self.store, "task", task.id, Status.DOING, actor="qa"),
        )

        snap = metrics.snapshot(
            self.store,
            now=1_500,
            plan_id=plan.id,
            scope_kind="task",
            scope_id=task.id,
        )

        assert snap.timeline is not None
        task_lane = next(lane for lane in snap.timeline.lanes if lane.kind == "task")
        self.assertEqual(task_lane.active, ((1_200, 1_300), (1_400, 1_500)))
        self.assertEqual(task_lane.trace, task_lane.active)

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

    def _task_plan(self) -> tuple[int, int, int, int, int]:
        plan = self._at(1_000, lambda: self.store.add_plan("Plan"))
        first = self._at(1_100, lambda: self.store.add_milestone(plan.id, "First"))
        second = self._at(1_200, lambda: self.store.add_milestone(plan.id, "Second"))
        one = self._at(1_150, lambda: self.store.add_task(first.id, "Task one"))
        two = self._at(1_160, lambda: self.store.add_task(first.id, "Task two"))
        self._at(1_170, lambda: self.store.add_task(second.id, "Task three"))
        return plan.id, first.id, second.id, one.id, two.id

    def test_milestone_scope_adds_its_task_lanes(self) -> None:
        plan_id, first_id, _second_id, one_id, two_id = self._task_plan()
        self._at(
            1_300,
            lambda: services.set_status(self.store, "task", one_id, Status.DOING, actor="qa"),
        )
        self._at(
            1_500,
            lambda: services.set_status(self.store, "task", one_id, Status.DONE, actor="qa"),
        )

        snap = metrics.snapshot(
            self.store,
            now=2_000,
            plan_id=plan_id,
            scope_kind="milestone",
            scope_id=first_id,
        )

        assert snap.timeline is not None
        self.assertEqual(
            [(lane.kind, lane.title) for lane in snap.timeline.lanes],
            [
                ("plan", "Plan"),
                ("milestone", "First"),
                ("milestone", "Second"),
                ("task", "Task one"),
                ("task", "Task two"),
            ],
        )
        task_one = snap.timeline.lanes[3]
        self.assertEqual(task_one.active, ((1_300, 1_500),))
        self.assertFalse(snap.timeline.lanes[0].selected)
        self.assertTrue(snap.timeline.lanes[1].selected)
        self.assertFalse(snap.timeline.lanes[2].selected)
        self.assertFalse(task_one.selected)
        self.assertFalse(snap.timeline.lanes[4].selected)

    def test_task_scope_adds_siblings_and_marks_the_selected_task(self) -> None:
        plan_id, first_id, _second_id, one_id, two_id = self._task_plan()

        snap = metrics.snapshot(
            self.store,
            now=2_000,
            plan_id=plan_id,
            scope_kind="task",
            scope_id=two_id,
        )

        assert snap.timeline is not None
        tasks = [lane for lane in snap.timeline.lanes if lane.kind == "task"]
        self.assertEqual([lane.title for lane in tasks], ["Task one", "Task two"])
        self.assertEqual([lane.selected for lane in tasks], [False, True])
        self.assertEqual([lane.selected for lane in snap.timeline.lanes[:3]], [False, False, False])
        self.assertEqual(snap.timeline.lanes[0].kind, "plan")
        self.assertEqual(snap.timeline.lanes[1].title, "First")
        self.assertEqual(snap.timeline.lanes[2].title, "Second")

    def test_plan_scope_marks_only_the_plan_lane(self) -> None:
        plan = self._at(1_000, lambda: self.store.add_plan("Plan"))
        self._at(1_100, lambda: self.store.add_milestone(plan.id, "First"))
        self._at(1_200, lambda: self.store.add_milestone(plan.id, "Second"))

        snap = metrics.snapshot(
            self.store,
            now=2_000,
            plan_id=plan.id,
            scope_kind="plan",
            scope_id=plan.id,
        )

        assert snap.timeline is not None
        self.assertEqual(
            [(lane.kind, lane.selected) for lane in snap.timeline.lanes],
            [("plan", True), ("milestone", False), ("milestone", False)],
        )

    def test_milestone_scope_marks_only_that_milestone(self) -> None:
        plan = self._at(1_000, lambda: self.store.add_plan("Plan"))
        first = self._at(1_100, lambda: self.store.add_milestone(plan.id, "First"))
        self._at(1_200, lambda: self.store.add_milestone(plan.id, "Second"))
        self._at(1_150, lambda: self.store.add_task(first.id, "Task"))

        snap = metrics.snapshot(
            self.store,
            now=2_000,
            plan_id=plan.id,
            scope_kind="milestone",
            scope_id=first.id,
        )

        assert snap.timeline is not None
        self.assertEqual(
            [(lane.kind, lane.title, lane.selected) for lane in snap.timeline.lanes],
            [
                ("plan", "Plan", False),
                ("milestone", "First", True),
                ("milestone", "Second", False),
                ("task", "Task", False),
            ],
        )

    def test_task_scope_marks_only_the_selected_task(self) -> None:
        plan_id, _first_id, _second_id, _one_id, two_id = self._task_plan()

        snap = metrics.snapshot(
            self.store,
            now=2_000,
            plan_id=plan_id,
            scope_kind="task",
            scope_id=two_id,
        )

        assert snap.timeline is not None
        self.assertEqual(
            [(lane.kind, lane.title, lane.selected) for lane in snap.timeline.lanes],
            [
                ("plan", "Plan", False),
                ("milestone", "First", False),
                ("milestone", "Second", False),
                ("task", "Task one", False),
                ("task", "Task two", True),
            ],
        )

    def test_scoped_view_without_a_scope_marks_no_lanes_selected(self) -> None:
        plan = self._at(1_000, lambda: self.store.add_plan("Plan"))
        self._at(1_100, lambda: self.store.add_milestone(plan.id, "Milestone"))

        snap = metrics.snapshot(self.store, now=2_000, plan_id=plan.id)

        assert snap.timeline is not None
        self.assertEqual([lane.selected for lane in snap.timeline.lanes], [False, False])

    def test_unscoped_view_marks_no_lanes_selected(self) -> None:
        self._at(1_000, lambda: self.store.add_plan("First plan"))
        self._at(2_000, lambda: self.store.add_plan("Second plan"))

        snap = metrics.snapshot(self.store, now=3_000)

        assert snap.timeline is not None
        self.assertEqual([lane.selected for lane in snap.timeline.lanes], [False, False])

    def test_unscoped_snapshot_does_not_add_task_lanes(self) -> None:
        self._task_plan()

        snap = metrics.snapshot(self.store, now=2_000, scope_kind="milestone", scope_id=1)

        assert snap.timeline is not None
        self.assertEqual([lane.kind for lane in snap.timeline.lanes], ["plan"])
        self.assertEqual([lane.selected for lane in snap.timeline.lanes], [False])

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
        self.assertEqual(snap.timeline.empty, "no plans yet")

    def test_empty_store_reports_no_plans(self) -> None:
        snap = metrics.snapshot(self.store, now=2_000)

        assert snap.timeline is not None
        self.assertEqual(snap.timeline.lanes, ())
        self.assertEqual(snap.timeline.empty, "no plans yet")

    def test_scoped_plan_without_milestones_reports_no_milestones(self) -> None:
        plan = self._at(1_000, lambda: self.store.add_plan("Plan"))

        snap = metrics.snapshot(self.store, now=2_000, plan_id=plan.id)

        assert snap.timeline is not None
        self.assertEqual(snap.timeline.lanes, ())
        self.assertEqual(snap.timeline.empty, "no milestones yet")


if __name__ == "__main__":
    unittest.main()
