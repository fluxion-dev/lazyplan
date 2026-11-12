"""Apply gates, verified snapshots, and abort-without-mutation behavior."""

from __future__ import annotations

import os
import sqlite3
import tempfile
import time
import unittest
from contextlib import closing
from pathlib import Path
from unittest import mock

from lazyplan import services
from lazyplan.core.entities import Status
from lazyplan.core.errors import MaintenanceBackupError
from lazyplan.services import maintenance
from lazyplan.store import Store
from lazyplan.store.session_pointer import binding_path


class TestMaintenanceApply(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "apply.db")
        self.store = Store(self.db)
        self.old = time.time() - 10 * 86400

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _backups(self) -> list[Path]:
        return sorted(Path(self.tmp.name).glob("*.bak-*"))

    def _seed_dead_events(self, count: int = 100) -> None:
        with closing(sqlite3.connect(self.db)) as conn:
            conn.executemany(
                "INSERT INTO events (ts, actor, kind, action, detail) VALUES (?, 'x', 'x', 'x', ?)",
                [(self.old, "dead " + "x" * 100) for _ in range(count)],
            )
            conn.commit()

    def _dead_events(self) -> int:
        with closing(sqlite3.connect(self.db)) as conn:
            return int(
                conn.execute("SELECT COUNT(*) FROM events WHERE detail LIKE 'dead %'").fetchone()[0]
            )

    def _old_done_plan(self, name: str) -> int:
        plan = self.store.add_plan(name)
        services.set_status(self.store, "plan", plan.id, Status.DONE)
        with closing(sqlite3.connect(self.db)) as conn:
            conn.execute(
                "UPDATE events SET ts=? WHERE detail LIKE ?",
                (self.old, f"plan #{plan.id} -> done%"),
            )
            conn.commit()
        return plan.id

    def test_preview_writes_nothing_and_creates_no_snapshot(self) -> None:
        self._seed_dead_events()
        preview = maintenance.trim(self.store, days="1", apply=False)
        self.assertFalse(preview.applied)
        self.assertEqual(self._dead_events(), 100)
        self.assertEqual(self._backups(), [])

        plan_id = self._old_done_plan("Old plan")
        session, _previous = self.store.start_session(
            "builder", plan_id=plan_id, repo_path=self.tmp.name, now=self.old
        )
        self.store.end_session(session.id, "builder", summary="done", now=self.old)
        archive = maintenance.archive(self.store, days="1", apply=False)
        self.assertIn(plan_id, archive.plans)
        self.assertIn(session.id, archive.sessions)
        row = self.store.get_plan(plan_id)
        assert row is not None
        self.assertEqual(row.archived_at, 0.0)
        self.assertEqual(self._backups(), [])

        vacuum = maintenance.vacuum(self.store, apply=False)
        self.assertFalse(vacuum.applied)
        self.assertEqual(self._backups(), [])

    def test_trim_apply_snapshots_before_the_first_delete(self) -> None:
        self._seed_dead_events()
        result = maintenance.trim(self.store, days="1", apply=True)
        self.assertTrue(result.applied)
        backups = self._backups()
        self.assertEqual(len(backups), 1)
        backup = backups[0]
        self.assertTrue(backup.is_file())
        self.assertEqual(self._dead_events(), 0)
        with closing(sqlite3.connect(backup)) as conn:
            self.assertEqual(str(conn.execute("PRAGMA integrity_check").fetchone()[0]), "ok")
            kept = int(
                conn.execute("SELECT COUNT(*) FROM events WHERE detail LIKE 'dead %'").fetchone()[0]
            )
        self.assertEqual(kept, 100)

    def test_failed_snapshot_aborts_without_mutation(self) -> None:
        self._seed_dead_events()
        with mock.patch.object(
            self.store,
            "backup",
            side_effect=MaintenanceBackupError("snapshot failed"),
        ):
            with self.assertRaises(MaintenanceBackupError):
                maintenance.trim(self.store, days="1", apply=True)
        self.assertEqual(self._dead_events(), 100)
        self.assertEqual(self._backups(), [])

    def test_archive_apply_snapshots_and_archives(self) -> None:
        plan_id = self._old_done_plan("Old plan")
        result = maintenance.archive(self.store, days="1", apply=True)
        self.assertTrue(result.applied)
        self.assertIn(plan_id, result.plans)
        row = self.store.get_plan(plan_id)
        assert row is not None
        self.assertGreater(row.archived_at, 0)
        self.assertEqual(len(self._backups()), 1)

    def test_vacuum_apply_snapshots_and_shrinks(self) -> None:
        with closing(sqlite3.connect(self.db)) as conn:
            conn.executemany(
                "INSERT INTO events (ts, actor, kind, action, detail) VALUES (?, 'x', 'x', 'x', ?)",
                [(time.time(), "spill " + "x" * 300) for _ in range(3_000)],
            )
            conn.execute("DELETE FROM events WHERE detail LIKE 'spill %'")
            conn.commit()
        before = os.path.getsize(self.db)
        result = maintenance.vacuum(self.store, apply=True)
        self.assertTrue(result.applied)
        self.assertLess(result.after_bytes, before)
        self.assertEqual(len(self._backups()), 1)

    def test_backup_snapshots_database_and_bindings(self) -> None:
        plan = self.store.add_plan("Plan")
        session, _previous = self.store.start_session(
            "builder", plan_id=plan.id, repo_path=self.tmp.name
        )
        self.store.bind_session("claude", "host-1", "project", self.tmp.name, session.id)
        binding = binding_path(self.db, "claude", "host-1", "project")
        self.assertTrue(binding.exists())

        result = self.store.backup("test")

        backup = Path(result.path)
        self.assertTrue(result.verified)
        self.assertTrue(backup.is_file())
        self.assertTrue(Path(f"{result.path}.bindings").is_dir())
        self.assertTrue((Path(f"{result.path}.bindings") / binding.name).exists())
        with closing(sqlite3.connect(backup)) as conn:
            self.assertEqual(str(conn.execute("PRAGMA integrity_check").fetchone()[0]), "ok")
            counts = {
                table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
                for table in ("plans", "tasks", "events")
            }
        self.assertEqual(counts["plans"], 1)

    def test_unverified_snapshot_is_removed_and_aborts(self) -> None:
        self.store.add_plan("Plan")
        with mock.patch.object(self.store, "_integrity_ok", return_value=False):
            with self.assertRaises(MaintenanceBackupError):
                self.store.backup()
        self.assertEqual(self._backups(), [])


if __name__ == "__main__":
    unittest.main()
