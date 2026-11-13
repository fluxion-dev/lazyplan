"""Legacy session history survives migration; the agent registry tables are dropped."""

from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from contextlib import closing

from lazyplan import services
from lazyplan.store import Store


class SessionHistoryStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = os.path.join(self.tmp.name, "agents.db")
        self.store = Store(self.db)
        self.plan = self.store.add_plan("Plan", actor="ana")
        self.milestone = self.store.add_milestone(self.plan.id, "M", actor="ana")
        self.task = self.store.add_task(self.milestone.id, "T", actor="ana")

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
        self.assertNotIn("agents", tables)

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
        self.assertNotIn("agents", tables)
        self.assertNotIn("agent_events", tables)
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

    def test_a_v15_database_drops_the_agent_registry_and_keeps_claims(self) -> None:
        self.store.claim_task(self.task.id, "ana", worktree="/w", repo_path="/w")
        with closing(sqlite3.connect(self.db)) as conn:
            conn.executescript(
                "CREATE TABLE agents (id INTEGER PRIMARY KEY);"
                "CREATE TABLE agent_events (id INTEGER PRIMARY KEY);"
                "INSERT INTO agents (id) VALUES (1);"
                "PRAGMA user_version = 15;"
            )
        store = Store(self.db)
        with closing(sqlite3.connect(self.db)) as conn:
            tables = {
                str(row[0])
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            version = conn.execute("PRAGMA user_version").fetchone()[0]
        self.assertNotIn("agents", tables)
        self.assertNotIn("agent_events", tables)
        self.assertEqual(version, 16)
        claim = store.get_claim(self.task.id)
        assert claim is not None
        self.assertEqual(claim.actor, "ana")
