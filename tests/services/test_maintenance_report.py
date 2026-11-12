"""Per-table maintenance report over a seeded database."""

from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from unittest import mock

from lazyplan.services import maintenance
from lazyplan.store import Store


class TestMaintenanceReport(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "report.db")
        self.store = Store(self.db)
        plan = self.store.add_plan("Plan", "what", goal="why")
        milestone = self.store.add_milestone(plan.id, "Milestone", "details")
        task = self.store.add_task(milestone.id, "Task", "task details")
        criterion = self.store.add_criteria("task", task.id, "Works")
        self.store.add_note("plan", plan.id, "handoff note")
        self.store.add_comment("task", task.id, "review comment")
        self.store.add_evidence(criterion.id, command="pytest", exit_code=0)
        self.store.add_touchpoint(task.id, "src/file.py")
        self.store.cache_put("cache-key", "etag", 1, "{}")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _schema_tables(self) -> set[str]:
        with closing(sqlite3.connect(self.db)) as conn:
            return {
                str(row[0])
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }

    def test_report_lists_every_table_with_bytes_and_rows(self) -> None:
        report = maintenance.report(self.store)
        self.assertEqual(report.method, "dbstat")
        listed = {row.table for row in report.tables}
        self.assertTrue(self._schema_tables() <= listed)
        for row in report.tables:
            if row.table == "sqlite_schema":
                continue
            with closing(sqlite3.connect(self.db)) as conn:
                expected = int(conn.execute(f'SELECT COUNT(*) FROM "{row.table}"').fetchone()[0])
            self.assertEqual(row.rows, expected, row.table)

    def test_table_bytes_account_for_the_file(self) -> None:
        report = maintenance.report(self.store)
        with closing(sqlite3.connect(self.db)) as conn:
            page_size = int(conn.execute("PRAGMA page_size").fetchone()[0])
        file_size = os.path.getsize(self.db)
        self.assertLessEqual(abs(report.total_bytes - file_size), page_size)
        self.assertLessEqual(
            abs(sum(row.bytes for row in report.tables) + report.free_bytes - file_size),
            page_size,
        )
        self.assertGreater(report.total_bytes, 0)

    def test_missing_dbstat_falls_back_to_page_counts(self) -> None:
        with mock.patch.object(
            Store,
            "_dbstat_bytes",
            side_effect=sqlite3.OperationalError("no such table: dbstat"),
        ):
            report = maintenance.report(self.store)
        self.assertEqual(report.method, "page_count")
        with closing(sqlite3.connect(self.db)) as conn:
            page_size = int(conn.execute("PRAGMA page_size").fetchone()[0])
            page_count = int(conn.execute("PRAGMA page_count").fetchone()[0])
        self.assertEqual(report.total_bytes, page_count * page_size)
        self.assertLessEqual(abs(report.total_bytes - os.path.getsize(self.db)), page_size)
        self.assertTrue(self._schema_tables() <= {row.table for row in report.tables})
        self.assertTrue(all(row.bytes == 0 for row in report.tables))


if __name__ == "__main__":
    unittest.main()
