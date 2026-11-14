"""Archived history stays out of coordination reads; live agents stay visible."""

from __future__ import annotations

import os
import tempfile
import unittest

from lazyplan import services
from lazyplan.core.entities import Status
from lazyplan.store import Store


class TestArchivedSessionReads(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "sessions.db")
        self.store = Store(self.db)
        self.plan = self.store.add_plan("Work")
        self.milestone = self.store.add_milestone(self.plan.id, "Slice")
        self.task = self.store.add_task(self.milestone.id, "Task")
        self.store.restore_session_history(
            {
                "id": 1,
                "actor": "builder",
                "plan_id": self.plan.id,
                "repo_path": self.tmp.name,
                "started_at": 100.0,
                "ended_at": 200.0,
                "summary": "done",
            }
        )
        self.store.archive_sessions([1], actor="builder", now=300.0)
        self.store.restore_session_history(
            {
                "id": 2,
                "actor": "reviewer",
                "plan_id": self.plan.id,
                "repo_path": self.tmp.name,
                "started_at": 400.0,
                "ended_at": 0.0,
            }
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_session_reads_hide_archived_rows(self) -> None:
        listed = [row.id for row in self.store.list_sessions()]
        self.assertEqual(listed, [2])
        only = [row.id for row in self.store.list_sessions(archived="only")]
        self.assertEqual(only, [1])
        shown = {row.id for row in self.store.list_sessions(archived="show")}
        self.assertEqual(shown, {1, 2})

    def test_explicit_session_read_still_finds_an_archived_row(self) -> None:
        row = self.store.get_session(1)
        assert row is not None
        self.assertGreater(row.archived_at, 0)

    def test_claims_and_next_skip_archived_plans(self) -> None:
        self.store.claim_task(self.task.id, "builder", ttl_seconds=600, now=500.0)
        self.store.set_status_raw("plan", self.plan.id, Status.DONE)
        self.store.archive_plan(self.plan.id, actor="builder", now=600.0)
        self.assertEqual(self.store.list_claims(now=700.0), [])
        self.assertEqual(self.store.claimable_tasks(now=700.0), [])
        self.assertIsNone(services.claim_next(self.store, "reviewer", plan_id=self.plan.id))


if __name__ == "__main__":
    unittest.main()
