"""The exact agent registry, its transition log, and legacy session history."""

from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from unittest import mock

from lazyplan import services
from lazyplan.store import Store


class AgentStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = os.path.join(self.tmp.name, "agents.db")
        self.store = Store(self.db)
        self.plan = self.store.add_plan("Plan", actor="ana")
        self.milestone = self.store.add_milestone(self.plan.id, "M", actor="ana")
        self.task = self.store.add_task(self.milestone.id, "T", actor="ana")

    def _agent(self, **fields: object):
        values: dict[str, object] = {
            "host": "opencode",
            "host_session": "host-1",
            "agent": "builder",
            "plan_id": self.plan.id,
            "worktree": self.store.checkout_path(),
        }
        values.update(fields)
        return self.store.add_agent("ana", **values)

    def test_schema_has_agents_events_wal_and_history(self) -> None:
        with closing(sqlite3.connect(self.db)) as conn:
            tables = {
                str(row[0])
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            indexes = {
                str(row[0])
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")
            }
            columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(agents)")}
            journal = str(conn.execute("PRAGMA journal_mode").fetchone()[0]).lower()
        self.assertIn("agents", tables)
        self.assertIn("agent_events", tables)
        self.assertIn("session_history", tables)
        self.assertNotIn("sessions", tables)
        self.assertEqual(journal, "wal")
        for name in (
            "host",
            "host_session",
            "agent",
            "role",
            "model",
            "parent_id",
            "pid",
            "process_start",
            "repo_path",
            "worktree",
            "branch",
            "head_sha",
            "plan_id",
            "task_id",
            "status",
            "unbound_reason",
        ):
            self.assertIn(name, columns)
        for name in (
            "idx_agents_open",
            "idx_agents_plan",
            "idx_agents_task",
            "idx_agents_host",
            "idx_agents_parent",
            "idx_agents_worktree",
            "idx_agent_events_agent",
        ):
            self.assertIn(name, indexes)

    def test_add_records_exact_identity_and_one_start_event(self) -> None:
        agent = self._agent(
            role="subagent",
            model="gpt-5",
            pid=4321,
            process_start="99",
            repo_path="/repo",
            branch="plan/1-agent",
            head_sha="a" * 40,
            task_id=self.task.id,
        )
        self.assertEqual(agent.host, "opencode")
        self.assertEqual(agent.host_session, "host-1")
        self.assertEqual(agent.agent, "builder")
        self.assertEqual(agent.model, "gpt-5")
        self.assertEqual(agent.pid, 4321)
        self.assertEqual(agent.task_id, self.task.id)
        events = self.store.agent_events(agent.id)
        self.assertEqual(
            [(event.event, event.to_status) for event in events], [("start", "starting")]
        )
        self.assertEqual(self.store.agent_counts(), {"starting": 1})

    def test_transitions_are_validated_and_logged_once(self) -> None:
        agent = self._agent()
        for status in ("working", "tool", "compacting", "waiting", "working"):
            moved = self.store.transition_agent(agent.id, status, event=f"to-{status}")
            self.assertEqual(moved.status, status)
        with self.assertRaises(ValueError):
            self.store.transition_agent(agent.id, "starting", event="back")
        with self.assertRaises(ValueError):
            self.store.transition_agent(agent.id, "nonsense", event="bad")
        self.assertEqual(len(self.store.agent_events(agent.id)), 6)

    def test_end_sets_one_timestamp_and_closes_live_children(self) -> None:
        parent = self._agent()
        child = self._agent(host_session="child-1", parent_id=parent.id, role="subagent")
        ended = self.store.end_agent(parent.id, "ana", summary="done", handoff="next: T2")
        self.assertEqual(ended.status, "ended")
        self.assertGreater(ended.ended_at, 0)
        self.assertEqual(ended.summary, "done")
        self.assertEqual(ended.handoff, "next: T2")
        self.assertEqual(self.store.get_agent(child.id).status, "ended")
        self.assertEqual(self.store.child_agents(parent.id, open_only=True), [])
        with self.assertRaises(ValueError):
            self.store.end_agent(parent.id, "ana")

    def test_binding_validation_rejects_a_task_from_another_plan(self) -> None:
        other = self.store.add_plan("Other", actor="ana")
        with self.assertRaises(ValueError):
            self.store.add_agent("ana", agent="x", plan_id=other.id, task_id=self.task.id)
        with self.assertRaises(KeyError):
            self.store.add_agent("ana", agent="x", parent_id=999)

    def test_list_filters_open_and_live_rows(self) -> None:
        first = self._agent()
        second = self._agent(host_session="host-2")
        self.store.end_agent(second.id, "ana")
        self.assertEqual([row.id for row in self.store.list_agents(open_only=True)], [first.id])
        self.assertEqual([row.id for row in self.store.list_agents(live_only=True)], [first.id])

    def test_liveness_marks_a_dead_pid_lost_and_never_revives_it(self) -> None:
        agent = self._agent(pid=999_999, process_start="1")
        with (
            mock.patch("lazyplan.services.agents.process_alive", return_value=False),
            mock.patch("lazyplan.infrastructure.process.process_start", return_value="1"),
        ):
            lost = services.sweep_lost(self.store)
        self.assertEqual([row.id for row in lost], [agent.id])
        self.assertEqual(self.store.get_agent(agent.id).status, "lost")
        self.assertEqual(services.sweep_lost(self.store), [])
        with self.assertRaises(ValueError):
            self.store.transition_agent(agent.id, "working", event="revive")

    def test_a_v14_database_keeps_every_session_id_and_summary(self) -> None:
        path = os.path.join(self.tmp.name, "v14.db")
        with closing(sqlite3.connect(path)) as conn:
            conn.executescript(
                """
                CREATE TABLE sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    actor TEXT NOT NULL DEFAULT 'human',
                    plan_id INTEGER,
                    repo_path TEXT NOT NULL DEFAULT '',
                    branch TEXT NOT NULL DEFAULT '',
                    started_at REAL NOT NULL,
                    ended_at REAL NOT NULL DEFAULT 0,
                    summary TEXT NOT NULL DEFAULT '',
                    handoff TEXT NOT NULL DEFAULT '',
                    phase TEXT NOT NULL DEFAULT 'working',
                    last_seen_at REAL NOT NULL DEFAULT 0,
                    host TEXT NOT NULL DEFAULT '',
                    host_session TEXT NOT NULL DEFAULT '',
                    auto_closed INTEGER NOT NULL DEFAULT 0,
                    plan_source TEXT NOT NULL DEFAULT 'auto',
                    archived_at REAL NOT NULL DEFAULT 0
                );
                """
            )
            conn.execute(
                "INSERT INTO sessions (id, actor, started_at, ended_at, summary)"
                " VALUES (7, 'ana', 100.0, 120.0, 'old work')"
            )
            conn.execute("PRAGMA user_version = 14")
            conn.commit()
        store = Store(path)
        legacy = store.get_session(7)
        assert legacy is not None
        self.assertEqual(legacy.summary, "old work")
        with closing(sqlite3.connect(path)) as conn:
            tables = {
                str(row[0])
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
        self.assertIn("session_history", tables)
        self.assertNotIn("sessions", tables)
        self.assertIn("agents", tables)

    def test_a_v12_database_keeps_every_legacy_session(self) -> None:
        path = os.path.join(self.tmp.name, "v12.db")
        with closing(sqlite3.connect(path)) as conn:
            conn.executescript(
                """
                CREATE TABLE sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    actor TEXT NOT NULL DEFAULT 'human',
                    plan_id INTEGER,
                    repo_path TEXT NOT NULL DEFAULT '',
                    branch TEXT NOT NULL DEFAULT '',
                    started_at REAL NOT NULL,
                    ended_at REAL NOT NULL DEFAULT 0,
                    summary TEXT NOT NULL DEFAULT '',
                    handoff TEXT NOT NULL DEFAULT '',
                    phase TEXT NOT NULL DEFAULT 'working',
                    last_seen_at REAL NOT NULL DEFAULT 0,
                    host TEXT NOT NULL DEFAULT '',
                    host_session TEXT NOT NULL DEFAULT '',
                    auto_closed INTEGER NOT NULL DEFAULT 0,
                    archived_at REAL NOT NULL DEFAULT 0
                );
                """
            )
            conn.execute(
                "INSERT INTO sessions (id, actor, started_at, ended_at, summary)"
                " VALUES (4, 'ana', 100.0, 120.0, 'kept')"
            )
            conn.execute("PRAGMA user_version = 12")
            conn.commit()
        store = Store(path)
        legacy = store.get_session(4)
        assert legacy is not None
        self.assertEqual(legacy.summary, "kept")
        self.assertEqual(legacy.actor, "ana")
        with closing(sqlite3.connect(path)) as conn:
            tables = {
                str(row[0])
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
        self.assertIn("agents", tables)
        self.assertIn("agent_events", tables)
        self.assertNotIn("sessions", tables)

    def test_history_export_round_trips_with_original_ids(self) -> None:
        path = os.path.join(self.tmp.name, "v14-round.db")
        with closing(sqlite3.connect(path)) as conn:
            conn.executescript(
                """
                CREATE TABLE sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    actor TEXT NOT NULL DEFAULT 'human',
                    plan_id INTEGER,
                    repo_path TEXT NOT NULL DEFAULT '',
                    branch TEXT NOT NULL DEFAULT '',
                    started_at REAL NOT NULL,
                    ended_at REAL NOT NULL DEFAULT 0,
                    summary TEXT NOT NULL DEFAULT '',
                    handoff TEXT NOT NULL DEFAULT '',
                    phase TEXT NOT NULL DEFAULT 'working',
                    last_seen_at REAL NOT NULL DEFAULT 0,
                    host TEXT NOT NULL DEFAULT '',
                    host_session TEXT NOT NULL DEFAULT '',
                    auto_closed INTEGER NOT NULL DEFAULT 0,
                    plan_source TEXT NOT NULL DEFAULT 'auto',
                    archived_at REAL NOT NULL DEFAULT 0
                );
                """
            )
            conn.execute(
                "INSERT INTO sessions (id, actor, started_at, ended_at, summary)"
                " VALUES (3, 'ana', 100.0, 120.0, 'shipped')"
            )
            conn.execute("PRAGMA user_version = 14")
            conn.commit()
        source = Store(path)
        dump = services.export_all(source)
        self.assertEqual(dump["session_history"][0]["id"], 3)
        target = Store(os.path.join(self.tmp.name, "import.db"))
        counts = services.import_all(target, dump)
        self.assertEqual(counts["session_history"], 1)
        restored = target.get_session(3)
        assert restored is not None
        self.assertEqual(restored.summary, "shipped")
