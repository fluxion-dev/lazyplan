"""Store persistence for sessions and event tagging."""

from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest import mock

from lazyplan.store import Store
from lazyplan.store import migrate as migrate_mod
from lazyplan.store.session_pointer import pointer_path, write_pointer


class TestSessionsStore(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "t.db")
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir()
        self.checkout = mock.patch(
            "lazyplan.infrastructure.checkout.checkout_path", return_value=self.repo
        )
        self.checkout.start()
        self.store = Store(self.db)
        self.plan = self.store.add_plan("Plan", actor="ana")
        self.milestone = self.store.add_milestone(self.plan.id, "M", actor="ana")
        self.task = self.store.add_task(self.milestone.id, "T", actor="ana")

    def tearDown(self) -> None:
        self.checkout.stop()
        self.tmp.cleanup()

    def session_events(self) -> list[dict]:
        return self.store.events_by_action("start", "end", "add")

    def test_schema_has_sessions_and_event_index(self) -> None:
        with closing(sqlite3.connect(self.db)) as conn:
            self.assertEqual(
                int(conn.execute("PRAGMA user_version").fetchone()[0]),
                migrate_mod.SCHEMA_VERSION,
            )
            tables = {
                str(row[0])
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            indexes = {
                str(row[0])
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")
            }
            columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(events)").fetchall()}
            session_columns = {
                str(row[1]) for row in conn.execute("PRAGMA table_info(sessions)").fetchall()
            }
        self.assertIn("sessions", tables)
        self.assertIn("session_id", columns)
        for name in ("phase", "last_seen_at", "host", "auto_closed"):
            self.assertIn(name, session_columns)
        for name in (
            "idx_sessions_open",
            "idx_sessions_plan",
            "idx_sessions_repo",
            "idx_events_session",
        ):
            self.assertIn(name, indexes)

    def test_start_tags_writes_for_the_same_actor(self) -> None:
        session, previous = self.store.start_session(
            "ana", plan_id=self.plan.id, branch="task/1", now=100.0
        )
        self.assertIsNone(previous)
        self.assertFalse(session.ended)
        self.store.add_task(self.milestone.id, "Second", actor="ana")
        self.store.add_task(self.milestone.id, "Other actor", actor="bo")
        rows = self.session_events()
        tagged = [row for row in rows if row["session_id"] == session.id]
        self.assertTrue(any(row["action"] == "add" for row in tagged))
        self.assertTrue(all(row["session_id"] is None for row in rows if row["actor"] == "bo"))
        self.assertEqual(self.store.session_counts(session.id).get("start"), 1)
        self.assertEqual(self.store.events_for_session(session.id)[0]["session_id"], session.id)

    def test_end_records_summary_handoff_and_clears_the_pointer(self) -> None:
        session, _ = self.store.start_session("ana", plan_id=self.plan.id, now=100.0)
        ended = self.store.end_session(
            session.id, "ana", summary=" shipped ", handoff=" next: T2 ", now=160.0
        )
        self.assertTrue(ended.ended)
        self.assertEqual(ended.summary, "shipped")
        self.assertEqual(ended.handoff, "next: T2")
        self.assertEqual(ended.duration(999.0), 60.0)
        self.assertFalse(pointer_path(self.db, "ana", self.repo).exists())
        self.assertEqual(self.store.latest_ended_session(plan_id=self.plan.id), ended)
        self.assertEqual(self.store.list_sessions(actor="ana"), [ended])

    def test_second_start_needs_force_and_ends_the_previous(self) -> None:
        first, _ = self.store.start_session("ana", now=100.0)
        with self.assertRaises(ValueError):
            self.store.start_session("ana", now=110.0)
        second, previous = self.store.start_session("ana", force=True, now=120.0)
        self.assertIsNotNone(previous)
        assert previous is not None
        self.assertEqual(previous.id, first.id)
        closed = self.store.get_session(first.id)
        assert closed is not None
        self.assertTrue(closed.ended)
        self.assertIn(f"S{second.id}", closed.summary)
        self.assertEqual(self.store.list_sessions(open_only=True), [second])

    def test_env_override_wins_over_the_checkout_pointer(self) -> None:
        session, _ = self.store.start_session("ana", now=100.0)
        other = Path(self.tmp.name) / "other"
        other.mkdir()
        with (
            mock.patch("lazyplan.infrastructure.checkout.checkout_path", return_value=other),
            mock.patch.dict(os.environ, {"LAZYPLAN_SESSION": f"S{session.id}"}),
        ):
            self.store.add_task(self.milestone.id, "Env write", actor="ana")
        row = self.store.events_for_session(session.id)[0]
        self.assertIn("Env write", row["detail"])

    def test_stale_pointer_to_an_ended_session_is_ignored(self) -> None:
        session, _ = self.store.start_session("ana", now=100.0)
        self.store.end_session(session.id, "ana", now=110.0)
        write_pointer(self.db, "ana", self.repo, session.id, 100.0)
        self.store.add_task(self.milestone.id, "Untagged", actor="ana")
        self.assertIsNone(self.store.events_by_action("add")[-1]["session_id"])

    def test_pointer_is_per_actor_and_checkout(self) -> None:
        first, _ = self.store.start_session("ana", now=100.0)
        other = Path(self.tmp.name) / "other"
        other.mkdir()
        with mock.patch("lazyplan.infrastructure.checkout.checkout_path", return_value=other):
            second, _ = self.store.start_session("ana", now=200.0)
        self.assertNotEqual(first.id, second.id)
        self.assertEqual(self.store.list_sessions(actor="ana", open_only=True), [second, first])
        self.assertEqual(self.store._resolve_session_id("ana"), first.id)

    def test_deleting_a_plan_keeps_the_session_without_a_plan(self) -> None:
        session, _ = self.store.start_session("ana", plan_id=self.plan.id, now=100.0)
        self.store.delete("plan", self.plan.id, actor="ana")
        kept = self.store.get_session(session.id)
        assert kept is not None
        self.assertIsNone(kept.plan_id)

    def test_end_unknown_or_ended_session_raises(self) -> None:
        with self.assertRaises(KeyError):
            self.store.end_session(99, "ana")
        session, _ = self.store.start_session("ana", now=100.0)
        self.store.end_session(session.id, "ana", now=110.0)
        with self.assertRaises(ValueError):
            self.store.end_session(session.id, "ana", now=120.0)

    def test_touch_updates_phase_and_heartbeat(self) -> None:
        session, _ = self.store.start_session("ana", now=100.0)
        touched = self.store.touch_session(session.id, phase="awaiting", host="claude", now=200.0)
        assert touched is not None
        self.assertTrue(touched.awaiting)
        self.assertEqual(touched.last_seen_at, 200.0)
        self.assertEqual(touched.host, "claude")
        self.assertEqual(touched.idle_seconds(260.0), 60.0)
        self.assertEqual(self.store.touch_session(999, now=300.0), None)

    def test_reap_closes_sessions_idle_past_the_threshold(self) -> None:
        session, _ = self.store.start_session("ana", now=100.0)
        self.assertEqual(self.store.reap_idle_sessions(now=200.0, repo_path=str(self.repo)), [])
        closed = self.store.reap_idle_sessions(now=100.0 + 7201, repo_path=str(self.repo))
        self.assertEqual([row.id for row in closed], [session.id])
        ended = self.store.get_session(session.id)
        assert ended is not None
        self.assertTrue(ended.ended)
        self.assertTrue(ended.auto_closed)
        self.assertIn("auto-closed", ended.summary)
        self.assertFalse(pointer_path(self.db, "ana", self.repo).exists())

    def test_start_reaps_a_stale_previous_session(self) -> None:
        first, _ = self.store.start_session("ana", now=100.0)
        second, previous = self.store.start_session("ana", now=100.0 + 7201)
        self.assertIsNone(previous)
        self.assertNotEqual(first.id, second.id)
        old = self.store.get_session(first.id)
        assert old is not None
        self.assertTrue(old.ended)
        self.assertTrue(old.auto_closed)

    def test_two_host_bindings_share_one_row_and_close_on_last_detach(self) -> None:
        session, _ = self.store.start_session("ana", now=100.0)
        self.store.bind_session("opencode", "host-a", "/project", str(self.repo), session.id, now=110.0)
        self.store.bind_session("opencode", "host-b", "/project", str(self.repo), session.id, now=120.0)
        self.assertEqual(self.store.session_for_project("/project", host="opencode"), session)
        detached, last = self.store.detach_host_binding("opencode", "host-a", "/project")
        assert detached is not None
        self.assertEqual(detached.id, session.id)
        self.assertFalse(last)
        self.assertFalse(detached.ended)
        detached, last = self.store.detach_host_binding("opencode", "host-b", "/project")
        assert detached is not None
        self.assertTrue(last)
        self.assertEqual(self.store.session_for_project("/project"), None)

    def test_project_binding_does_not_leak_to_another_checkout(self) -> None:
        session, _ = self.store.start_session("ana", repo_path=str(self.repo), now=100.0)
        self.store.bind_session("opencode", "host-a", "/project-a", str(self.repo), session.id, now=110.0)
        self.assertEqual(self.store.session_for_project("/project-a"), session)
        self.assertIsNone(self.store.session_for_project("/project-b"))

    def test_tagged_writes_heartbeat_and_ended_sessions_stay_frozen(self) -> None:
        session, _ = self.store.start_session("ana", now=100.0)
        self.store.log("ana", "task", "move", "moved", now=200.0)
        touched = self.store.get_session(session.id)
        assert touched is not None
        self.assertEqual(touched.last_seen_at, 200.0)
        self.store.end_session(session.id, "ana", now=210.0)
        self.store.log("ana", "task", "move", "after end", now=300.0)
        ended = self.store.get_session(session.id)
        assert ended is not None
        self.assertEqual(ended.last_seen_at, 210.0)

    def test_v8_database_gains_session_state(self) -> None:
        path = os.path.join(self.tmp.name, "v8.db")
        with closing(sqlite3.connect(path)) as conn:
            conn.executescript(migrate_mod.SCHEMA)
            for column in ("phase", "last_seen_at", "host", "auto_closed"):
                conn.execute(f"ALTER TABLE sessions DROP COLUMN {column}")
            conn.execute("PRAGMA user_version = 8")
            conn.execute(
                "INSERT INTO sessions (actor, started_at, ended_at) VALUES ('ana', 100.0, 0)"
            )
            conn.commit()
        store = Store(path)
        session = store.get_session(1)
        assert session is not None
        self.assertEqual(session.phase, "working")
        self.assertEqual(session.last_seen_at, 100.0)
        self.assertEqual(session.host, "")
        self.assertFalse(session.auto_closed)

    def test_v5_database_gains_sessions_and_the_event_column(self) -> None:
        path = os.path.join(self.tmp.name, "v5.db")
        with closing(sqlite3.connect(path)) as conn:
            conn.executescript(migrate_mod.SCHEMA)
            conn.execute("DROP INDEX IF EXISTS idx_events_session")
            conn.execute("ALTER TABLE events DROP COLUMN session_id")
            conn.execute("DROP TABLE sessions")
            conn.execute("PRAGMA user_version = 5")
            conn.execute(
                "INSERT INTO plans (name, description, status, goal, uid)"
                " VALUES ('Old', '', 'todo', '', 'uid-old')"
            )
            conn.commit()
        store = Store(path)
        session, _ = store.start_session("ana", now=100.0)
        store.add_plan("New", actor="ana")
        loaded = store.get_session(session.id)
        assert loaded is not None
        self.assertEqual(loaded.id, session.id)
        self.assertEqual(loaded.started_at, session.started_at)
        self.assertEqual(loaded.phase, session.phase)
        self.assertGreater(loaded.last_seen_at, session.last_seen_at)
        self.assertEqual(store.session_counts(session.id).get("start"), 1)


if __name__ == "__main__":
    unittest.main()
