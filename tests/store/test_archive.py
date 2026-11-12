"""Archive and restore persistence for plans and sessions."""

from __future__ import annotations

import os
import tempfile
import unittest

from lazyplan.store import Store
from lazyplan.store.session_pointer import binding_path, bindings_for_session


class TestStoreArchive(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "archive.db")
        self.store = Store(self.db)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _events(self, kind: str, action: str) -> list[dict]:
        return [
            event
            for event in self.store.feed(limit=500)
            if event["kind"] == kind and event["action"] == action
        ]

    def test_archive_plan_stamps_and_logs_once(self) -> None:
        plan = self.store.add_plan("Old work")
        self.assertTrue(self.store.archive_plan(plan.id, actor="builder", now=123.0))
        stored = self.store.get_plan(plan.id)
        assert stored is not None
        self.assertEqual(stored.archived_at, 123.0)
        self.assertEqual(len(self._events("plan", "archive")), 1)

        self.assertFalse(self.store.archive_plan(plan.id, actor="builder", now=456.0))
        again = self.store.get_plan(plan.id)
        assert again is not None
        self.assertEqual(again.archived_at, 123.0)
        self.assertEqual(len(self._events("plan", "archive")), 1)

    def test_archive_sessions_keeps_claims_made_after_the_session_ended(self) -> None:
        plan = self.store.add_plan("Work")
        milestone = self.store.add_milestone(plan.id, "Slice")
        task = self.store.add_task(milestone.id, "Task")
        session, _previous = self.store.start_session(
            "builder", plan_id=plan.id, repo_path=self.tmp.name, now=100.0
        )
        self.store.end_session(session.id, "builder", summary="done", now=200.0)
        self.store.claim_task(
            task.id, "builder", ttl_seconds=10_000, now=300.0, repo_path=self.tmp.name
        )

        self.assertEqual(self.store.archive_sessions([session.id], actor="builder", now=400.0), 1)

        self.assertIsNotNone(self.store.get_claim(task.id))

    def test_restore_plan_clears_and_logs_once(self) -> None:
        plan = self.store.add_plan("Old work")
        self.store.archive_plan(plan.id, actor="builder", now=123.0)
        self.assertTrue(self.store.restore_plan(plan.id, actor="builder", now=456.0))
        stored = self.store.get_plan(plan.id)
        assert stored is not None
        self.assertEqual(stored.archived_at, 0.0)
        self.assertEqual(len(self._events("plan", "restore")), 1)

        self.assertFalse(self.store.restore_plan(plan.id, actor="builder"))
        self.assertEqual(len(self._events("plan", "restore")), 1)

    def test_archive_sessions_skips_open_rows_and_removes_bindings(self) -> None:
        plan = self.store.add_plan("Work")
        ended, _previous = self.store.start_session(
            "builder", plan_id=plan.id, repo_path=self.tmp.name, now=100.0
        )
        self.store.end_session(ended.id, "builder", summary="done", now=200.0)
        self.store.bind_session("claude", "host-1", "project", self.tmp.name, ended.id)
        binding = binding_path(self.db, "claude", "host-1", "project")
        self.assertTrue(binding.exists())

        open_row, _previous = self.store.start_session(
            "other", plan_id=plan.id, repo_path=self.tmp.name, now=300.0
        )
        self.assertEqual(self.store.archive_sessions([open_row.id], actor="builder", now=500.0), 0)
        still_open = self.store.get_session(open_row.id)
        assert still_open is not None
        self.assertEqual(still_open.archived_at, 0.0)

        self.assertEqual(self.store.archive_sessions([ended.id], actor="builder", now=500.0), 1)
        archived = self.store.get_session(ended.id)
        assert archived is not None
        self.assertEqual(archived.archived_at, 500.0)
        self.assertFalse(binding.exists())
        self.assertEqual(bindings_for_session(self.db, ended.id), [])
        session_events = [
            event for event in self._events("session", "archive") if event["session_id"] == ended.id
        ]
        self.assertEqual(len(session_events), 1)

        self.assertEqual(self.store.archive_sessions([ended.id], actor="builder", now=600.0), 0)
        self.assertTrue(self.store.restore_session(ended.id, actor="builder", now=700.0))
        restored = self.store.get_session(ended.id)
        assert restored is not None
        self.assertEqual(restored.archived_at, 0.0)
        self.assertFalse(self.store.restore_session(ended.id, actor="builder"))


if __name__ == "__main__":
    unittest.main()
