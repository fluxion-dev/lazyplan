"""Archived plans stay out of every planning read surface."""

from __future__ import annotations

import os
import tempfile
import unittest

from lazyplan import services
from lazyplan.core.entities import Status
from lazyplan.services import audit, brief, ready, stats, trace
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
        services.set_status(self.store, "plan", self.archived.id, Status.DONE)
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

    def test_trace_hides_archived_plan_and_its_criteria(self) -> None:
        self.assertIsNone(trace.trace_plan(self.store, self.archived.id))
        self.assertIsNone(trace.trace_criterion(self.store, self.criterion.id))
        self.assertIsNotNone(trace.trace_plan(self.store, self.live.id))


if __name__ == "__main__":
    unittest.main()
