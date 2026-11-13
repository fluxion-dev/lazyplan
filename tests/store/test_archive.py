"""Archive and restore persistence for plans and session history."""

from __future__ import annotations

import os
import tempfile
import unittest

from lazyplan.core.entities import Status
from lazyplan.store import Store


class TestStoreArchive(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "archive.db")
        self.store = Store(self.db)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _events(self, kind: str, action: str) -> list[dict]:
        return [event for event in self.store.events_by_action(action) if event["kind"] == kind]

    def _history(self, session_id: int, ended_at: float, summary: str = "done") -> None:
        self.store.restore_session_history(
            {
                "id": session_id,
                "actor": "builder",
                "repo_path": self.tmp.name,
                "started_at": 100.0,
                "ended_at": ended_at,
                "summary": summary,
            }
        )

    def test_archive_plan_stamps_and_logs_once(self) -> None:
        plan = self.store.add_plan("Old work")
        self.store.set_status_raw("plan", plan.id, Status.DONE)
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

    def test_archive_sessions_keeps_claims_made_after_history_ended(self) -> None:
        plan = self.store.add_plan("Work")
        milestone = self.store.add_milestone(plan.id, "Slice")
        task = self.store.add_task(milestone.id, "Task")
        self._history(1, ended_at=200.0)
        self.store.claim_task(task.id, "builder", ttl_seconds=10_000, now=300.0)

        self.assertEqual(self.store.archive_sessions([1], actor="builder", now=400.0), 1)
        self.assertIsNotNone(self.store.get_claim(task.id))

    def test_restore_plan_clears_and_logs_once(self) -> None:
        plan = self.store.add_plan("Old work")
        self.store.set_status_raw("plan", plan.id, Status.DONE)
        self.store.archive_plan(plan.id, actor="builder", now=123.0)
        self.assertTrue(self.store.restore_plan(plan.id, actor="builder", now=456.0))
        stored = self.store.get_plan(plan.id)
        assert stored is not None
        self.assertEqual(stored.archived_at, 0.0)
        self.assertEqual(len(self._events("plan", "restore")), 1)

        self.assertFalse(self.store.restore_plan(plan.id, actor="builder"))
        self.assertEqual(len(self._events("plan", "restore")), 1)

    def test_archive_sessions_skips_open_rows(self) -> None:
        self._history(1, ended_at=200.0)
        self.store.restore_session_history(
            {"id": 2, "actor": "other", "started_at": 300.0, "ended_at": 0.0}
        )
        self.assertEqual(self.store.archive_sessions([2], actor="builder", now=500.0), 0)
        still_open = self.store.get_session(2)
        assert still_open is not None
        self.assertEqual(still_open.archived_at, 0.0)

        self.assertEqual(self.store.archive_sessions([1], actor="builder", now=500.0), 1)
        archived = self.store.get_session(1)
        assert archived is not None
        self.assertEqual(archived.archived_at, 500.0)
        session_events = [
            event for event in self._events("session", "archive") if event["session_id"] == 1
        ]
        self.assertEqual(len(session_events), 1)

        self.assertEqual(self.store.archive_sessions([1], actor="builder", now=600.0), 0)
        self.assertTrue(self.store.restore_session(1, actor="builder", now=700.0))
        restored = self.store.get_session(1)
        assert restored is not None
        self.assertEqual(restored.archived_at, 0.0)
        self.assertFalse(self.store.restore_session(1, actor="builder"))

    def test_feed_retains_history_for_archived_plans(self) -> None:
        old = self.store.add_plan("Old plan")
        self.store.set_status_raw("plan", old.id, Status.DONE)
        self.store.archive_plan(old.id, actor="builder")
        live = self.store.add_plan("Live plan")

        details = [event["detail"] for event in self.store.feed(50)]

        self.assertTrue(any(f"P#{old.id} " in detail for detail in details))
        self.assertTrue(any(live.name in detail for detail in details))


if __name__ == "__main__":
    unittest.main()
