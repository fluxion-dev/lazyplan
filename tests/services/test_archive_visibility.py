"""Archived plans stay out of every planning read surface."""

from __future__ import annotations

import os
import tempfile
import time
import unittest

from lazyplan import services
from lazyplan.core.entities import Status
from lazyplan.services import (
    audit,
    brief,
    context,
    maintenance,
    ready,
    review,
    stats,
    trace,
)
from lazyplan.store import Store


class TestArchivedPlanReads(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "reads.db")
        self.store = Store(self.db)
        self.archived = self.store.add_plan("Archived plan", goal="old")
        self.milestone = self.store.add_milestone(self.archived.id, "Old slice")
        self.task = self.store.add_task(self.milestone.id, "Old task")
        self.doing = self.store.add_task(self.milestone.id, "Old doing task")
        self.store.set_status_raw("task", self.doing.id, Status.DOING)
        services.set_status(self.store, "task", self.task.id, Status.DONE)
        self.store.set_status_raw("plan", self.archived.id, Status.DONE)
        self.store.archive_plan(self.archived.id, actor="builder")
        self.criterion = self.store.add_criteria("plan", self.archived.id, "Old proof")
        self.live = self.store.add_plan("Live plan")
        services.set_status(self.store, "plan", self.live.id, Status.DOING)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_store_list_plans_honors_the_archive_view(self) -> None:
        self.assertEqual(
            [plan.id for plan in self.store.list_plans(archived="hide")], [self.live.id]
        )
        self.assertEqual(
            [plan.id for plan in self.store.list_plans(archived="only")], [self.archived.id]
        )
        self.assertEqual(
            {plan.id for plan in self.store.list_plans(archived="show")},
            {self.live.id, self.archived.id},
        )

    def test_tree_hides_by_default_and_reveals_on_request(self) -> None:
        default = [plan.id for plan, _ in services.tree(self.store)]
        self.assertEqual(default, [self.live.id])
        only = [plan.id for plan, _ in services.tree(self.store, archived="only")]
        self.assertEqual(only, [self.archived.id])
        shown = {plan.id for plan, _ in services.tree(self.store, archived="show")}
        self.assertEqual(shown, {self.live.id, self.archived.id})

    def test_brief_skips_archived_plans(self) -> None:
        payload = brief.build(self.store)
        self.assertEqual([plan["id"] for plan in payload["plans"]], [self.live.id])
        self.assertEqual(brief.build(self.store, plan_id=self.archived.id)["plans"], [])

    def test_ready_treats_archived_as_missing(self) -> None:
        self.assertIsNone(ready.check(self.store, self.archived.id))
        self.assertIsNotNone(ready.check(self.store, self.live.id))

    def test_stats_ignores_archived_tasks_and_parents(self) -> None:
        drift = stats.drift_summary(self.store)
        self.assertEqual(drift["parent_status"], [])
        metrics = stats.compute(self.store, since=0.0, stale_before=0.0)
        self.assertEqual(metrics["wip"], 0)
        self.assertNotIn(self.task.id, stats.attention_ids(self.store))

    def test_audit_skips_archived_plans(self) -> None:
        explicit = audit.report(self.store, plan_ids=[self.archived.id], cwd=self.tmp.name)
        self.assertEqual(explicit.plans, [])
        default = audit.report(self.store, since=0.0, cwd=self.tmp.name)
        self.assertNotIn(self.archived.id, default.plans)

    def test_tree_archive_reveal_includes_finished_plans(self) -> None:
        self.store.log(
            "fixture",
            "plan",
            "status",
            f"plan #{self.archived.id} -> done",
            now=time.time() - 3 * 86400,
        )
        finished = self.store.add_plan("Finished plan")
        services.set_status(self.store, "plan", finished.id, Status.DONE)
        self.store.log(
            "fixture",
            "plan",
            "status",
            f"plan #{finished.id} -> done",
            now=time.time() - 3 * 86400,
        )

        default = [row[0].id for row in services.tree(self.store)]
        only = [row[0].id for row in services.tree(self.store, archived="only")]
        shown = [row[0].id for row in services.tree(self.store, archived="show")]

        self.assertNotIn(self.archived.id, default)
        self.assertIn(self.archived.id, only)
        self.assertIn(finished.id, shown)

    def test_metrics_can_show_an_explicit_archived_plan(self) -> None:
        from lazyplan.services import metrics

        snapshot = metrics.snapshot(self.store, plan_id=self.archived.id)
        self.assertEqual(snapshot.plan_id, self.archived.id)
        self.assertEqual(snapshot.plan_title, "Archived plan")
        self.assertTrue(snapshot.timeline.lanes)

    def test_trace_hides_archived_plan_and_its_criteria(self) -> None:
        self.assertIsNone(trace.trace_plan(self.store, self.archived.id))
        self.assertIsNone(trace.trace_criterion(self.store, self.criterion.id))
        self.assertIsNotNone(trace.trace_plan(self.store, self.live.id))

    def test_context_and_review_cannot_see_archived_plan(self) -> None:
        self.assertEqual(context.build(self.store, plan_id=self.archived.id)["active"], 0)
        active = review.active_plan(self.store)
        assert active is not None
        self.assertEqual(active.id, self.live.id)
        self.assertEqual(self.store.list_plans()[0].id, self.live.id)

    def test_archive_requires_a_done_plan(self) -> None:
        self.assertFalse(self.store.archive_plan(self.live.id, actor="builder"))
        row = self.store.get_plan(self.live.id)
        assert row is not None
        self.assertEqual(row.archived_at, 0.0)

    def test_archive_rechecks_candidates_inside_the_write(self) -> None:
        from unittest import mock

        calls: list[int] = []

        def fake(port: object, stamp: float, window: float) -> tuple:
            del port, stamp, window
            calls.append(1)
            return ((self.live.id,), ()) if len(calls) == 1 else ((), ())

        with mock.patch.object(maintenance, "_archive_candidates", side_effect=fake):
            result = maintenance.archive(self.store, apply=True)
        self.assertEqual(result.plans, ())
        row = self.store.get_plan(self.live.id)
        assert row is not None
        self.assertEqual(row.archived_at, 0.0)


if __name__ == "__main__":
    unittest.main()
