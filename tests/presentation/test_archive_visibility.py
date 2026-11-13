"""End-to-end: an archived plan leaves every read surface and comes back."""

from __future__ import annotations

import io
import os
import tempfile
import time
import unittest
from contextlib import redirect_stdout

from lazyplan import services
from lazyplan.core.entities import Status
from lazyplan.presentation.cli import main as lpui_main
from lazyplan.services import audit, brief, ready, stats, trace
from lazyplan.store import Store


class TestArchiveVisibility(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db = os.path.join(self.tmp.name, "visible.db")
        self.store = Store(self.db)
        self.archived = self.store.add_plan("Archived plan", goal="shelved")
        self.milestone = self.store.add_milestone(self.archived.id, "Old slice")
        self.todo = self.store.add_task(self.milestone.id, "Queued task")
        self.doing = self.store.add_task(self.milestone.id, "Active task")
        self.store.set_status_raw("task", self.doing.id, Status.DOING)
        self.criterion = self.store.add_criteria("plan", self.archived.id, "Old proof")
        self.live = self.store.add_plan("Live plan")
        self.live_milestone = self.store.add_milestone(self.live.id, "Live slice")
        self.live_task = self.store.add_task(self.live_milestone.id, "Live task")
        self.store.set_status_raw("plan", self.archived.id, Status.DONE)
        self.store.log(
            "fixture",
            "plan",
            "status",
            f"plan #{self.archived.id} -> done",
            now=time.time() - 2 * 86400,
        )
        self.store.archive_plan(self.archived.id, actor="builder")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _list(self, *argv: str) -> str:
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(lpui_main(["--db", self.db, *argv]), 0)
        return out.getvalue()

    def test_archived_plan_is_absent_from_every_read_surface(self) -> None:
        listed = self._list("list", "--status", "all")
        self.assertNotIn("Archived plan", listed)
        self.assertIn("Live plan", listed)

        tree_ids = {plan.id for plan, _ in services.tree(self.store)}
        self.assertEqual(tree_ids, {self.live.id})

        self.assertEqual(brief.build(self.store, plan_id=self.archived.id)["plans"], [])
        self.assertEqual([plan["id"] for plan in brief.build(self.store)["plans"]], [self.live.id])

        self.assertIsNone(
            services.claim_next(self.store, "builder", plan_id=self.archived.id, suggest=True)
        )
        self.assertIsNone(ready.check(self.store, self.archived.id))
        self.assertEqual(stats.compute(self.store, since=0.0, stale_before=0.0)["wip"], 0)
        self.assertEqual(
            audit.report(self.store, plan_ids=[self.archived.id], cwd=self.tmp.name).plans, []
        )
        self.assertIsNone(trace.trace_plan(self.store, self.archived.id))
        self.assertIsNone(trace.trace_criterion(self.store, self.criterion.id))

    def test_archive_flag_reveals_only_when_asked(self) -> None:
        only = self._list("list", "--archived", "only")
        self.assertIn("Archived plan", only)
        self.assertNotIn("Live plan", only)
        both = self._list("list", "--archived", "all")
        self.assertIn("Archived plan", both)
        self.assertIn("Live plan", both)

    def test_restore_returns_a_done_plan_to_the_finished_views(self) -> None:
        self.assertTrue(self.store.restore_plan(self.archived.id, actor="builder"))

        self.assertIn("Archived plan", self._list("list", "--status", "all"))
        self.assertIn("Archived plan", self._list("list", "--finished"))
        default_tree = {plan.id for plan, _ in services.tree(self.store)}
        self.assertEqual(default_tree, {self.live.id})
        finished_tree = {plan.id for plan, _ in services.tree(self.store, finished="show")}
        self.assertEqual(finished_tree, {self.archived.id, self.live.id})
        self.assertEqual(
            [plan["id"] for plan in brief.build(self.store, plan_id=self.archived.id)["plans"]],
            [self.archived.id],
        )
        self.assertIsNone(
            services.claim_next(self.store, "builder", plan_id=self.archived.id, suggest=True)
        )
        self.assertIsNotNone(ready.check(self.store, self.archived.id))
        self.assertGreater(
            stats.compute(self.store, since=0.0, stale_before=0.0)["wip"],
            0,
        )
        self.assertEqual(
            audit.report(self.store, plan_ids=[self.archived.id], cwd=self.tmp.name).plans,
            [self.archived.id],
        )
        self.assertIsNotNone(trace.trace_plan(self.store, self.archived.id))
        self.assertIsNotNone(trace.trace_criterion(self.store, self.criterion.id))


if __name__ == "__main__":
    unittest.main()
