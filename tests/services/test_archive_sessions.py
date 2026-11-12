"""Archived sessions and archived plans stay out of coordination reads."""

from __future__ import annotations

import os
import tempfile
import unittest

from lazyplan import services
from lazyplan.services import needs_me
from lazyplan.store import Store


class TestArchivedSessionReads(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "sessions.db")
        self.store = Store(self.db)
        self.plan = self.store.add_plan("Work")
        self.milestone = self.store.add_milestone(self.plan.id, "Slice")
        self.task = self.store.add_task(self.milestone.id, "Task")
        self.session, _previous = self.store.start_session(
            "builder", plan_id=self.plan.id, repo_path=self.tmp.name, now=100.0
        )
        self.store.end_session(self.session.id, "builder", summary="done", now=200.0)
        self.store.archive_sessions([self.session.id], actor="builder", now=300.0)
        self.live, _previous = self.store.start_session(
            "reviewer", plan_id=self.plan.id, repo_path=self.tmp.name, now=400.0
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_session_reads_hide_archived_rows(self) -> None:
        listed = [row.id for row in self.store.list_sessions()]
        self.assertEqual(listed, [self.live.id])
        only = [row.id for row in self.store.list_sessions(archived="only")]
        self.assertEqual(only, [self.session.id])
        shown = {row.id for row in self.store.list_sessions(archived="show")}
        self.assertEqual(shown, {self.live.id, self.session.id})

    def test_explicit_session_read_still_finds_an_archived_row(self) -> None:
        row = self.store.get_session(self.session.id)
        assert row is not None
        self.assertGreater(row.archived_at, 0)

    def test_previous_session_skips_archived_rows(self) -> None:
        self.assertIsNone(self.store.latest_ended_session(plan_id=self.plan.id))
        self.assertIsNone(services.previous_session(self.store, plan_id=self.plan.id))

    def test_needs_me_does_not_list_archived_sessions(self) -> None:
        payload = needs_me.build(self.store)
        self.assertEqual([row["id"] for row in payload["sessions"]], [self.live.id])

    def test_claims_and_next_skip_archived_plans(self) -> None:
        self.store.claim_task(self.task.id, "builder", ttl_seconds=600, now=500.0)
        self.store.archive_plan(self.plan.id, actor="builder", now=600.0)
        self.assertEqual(self.store.list_claims(now=700.0), [])
        self.assertEqual(self.store.claimable_tasks(now=700.0), [])
        self.assertIsNone(services.claim_next(self.store, "reviewer", plan_id=self.plan.id))

    def test_reap_closes_but_never_archives_an_open_session(self) -> None:
        closed = self.store.reap_idle_sessions(now=10_000.0, idle_after=1.0)
        self.assertEqual([row.id for row in closed], [self.live.id])
        row = self.store.get_session(self.live.id)
        assert row is not None
        self.assertTrue(row.ended)
        self.assertEqual(row.archived_at, 0.0)


if __name__ == "__main__":
    unittest.main()
