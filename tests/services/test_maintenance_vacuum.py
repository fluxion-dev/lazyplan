"""Vacuum reclaims free pages and fails fast against a competing writer."""

from __future__ import annotations

import os
import sqlite3
import tempfile
import time
import unittest
from contextlib import closing

from lazyplan.core.errors import MaintenanceBusy
from lazyplan.services import maintenance
from lazyplan.store import Store


class TestMaintenanceVacuum(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "vacuum.db")
        self.store = Store(self.db)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _seed_dead_events(self, count: int = 4_000) -> None:
        old = time.time() - 10 * 86400
        with closing(sqlite3.connect(self.db)) as conn:
            conn.executemany(
                "INSERT INTO events (ts, actor, kind, action, detail) VALUES (?, 'x', 'x', 'x', ?)",
                [(old, "dead " + "x" * 200) for _ in range(count)],
            )
            conn.commit()

    def test_vacuum_reports_sizes_and_shrinks(self) -> None:
        self._seed_dead_events()
        maintenance.trim(self.store, days="1", apply=True)
        before_bytes = os.path.getsize(self.db)
        with closing(sqlite3.connect(self.db)) as conn:
            before_free = int(conn.execute("PRAGMA freelist_count").fetchone()[0])
        self.assertGreater(before_free, 0)

        result = maintenance.vacuum(self.store)

        self.assertTrue(result.applied)
        self.assertEqual(result.before_bytes, before_bytes)
        self.assertEqual(result.after_bytes, os.path.getsize(self.db))
        self.assertLess(result.after_bytes, result.before_bytes)
        self.assertEqual(result.before_free_pages, before_free)
        self.assertLess(result.after_free_pages, result.before_free_pages)
        self.assertGreater(result.freed_bytes, 0)

    def test_vacuum_fails_fast_when_the_database_is_busy(self) -> None:
        locker = sqlite3.connect(self.db, isolation_level=None)
        try:
            locker.execute("BEGIN EXCLUSIVE")
            started = time.monotonic()
            with self.assertRaises(MaintenanceBusy):
                self.store.vacuum()
            self.assertLess(time.monotonic() - started, 5.0)
        finally:
            locker.rollback()
            locker.close()


if __name__ == "__main__":
    unittest.main()
