"""Maintenance parity: CLI, MCP, and the screen agree on one fixture."""

from __future__ import annotations

import io
import json
import os
import sqlite3
import tempfile
import time
import unittest
from contextlib import closing, redirect_stderr, redirect_stdout
from unittest import mock

from lazyplan import services
from lazyplan.core.entities import Status
from lazyplan.core.errors import MaintenanceBackupError
from lazyplan.presentation.cli import main as lpui_main
from lazyplan.presentation.mcp.server import McpServer
from lazyplan.store import Store

try:
    from lazyplan.presentation.tui.screens.maintenance import MaintenanceScreen
except ImportError:  # pragma: no cover - textual not installed
    MaintenanceScreen = None  # type: ignore[assignment]


class TestMaintenanceParity(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "parity.db")
        self.store = Store(self.db)
        self.plan = self.store.add_plan("Live plan")
        self.milestone = self.store.add_milestone(self.plan.id, "Slice")
        self.task = self.store.add_task(self.milestone.id, "Task")
        self.old = time.time() - 10 * 86400
        self._seed()
        self.server = McpServer(self.store, actor="qa")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _seed(self) -> None:
        old_plan = self.store.add_plan("Old plan")
        services.set_status(self.store, "plan", old_plan.id, Status.DONE)
        session, _previous = self.store.start_session(
            "builder", plan_id=old_plan.id, repo_path=self.tmp.name, now=self.old
        )
        self.store.end_session(session.id, "builder", summary="done", now=self.old)
        self.store.claim_task(
            self.task.id, "builder", ttl_seconds=60, now=self.old, repo_path=self.tmp.name
        )
        self.store.cache_put("old-cache", "e", self.old, "{}")
        self.store.link_forge("task", self.task.id, 1, state="closed", title="old PR")
        with closing(sqlite3.connect(self.db)) as conn:
            conn.execute(
                "INSERT INTO events (ts, actor, kind, action, detail) VALUES (?, 'x', 'x', 'x', 'old')",
                (self.old,),
            )
            conn.execute("UPDATE events SET ts=? WHERE detail LIKE 'plan #% -> done%'", (self.old,))
            conn.execute(
                "INSERT INTO notes (parent_kind, parent_id, actor, ts, text)"
                " VALUES ('plan', 999999, 'x', ?, 'orphan')",
                (self.old,),
            )
            conn.commit()

    def _cli(self, *argv: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = lpui_main(["--db", self.db, *argv])
        return code, out.getvalue(), err.getvalue()

    def _cli_json(self, *argv: str) -> dict:
        code, out, err = self._cli("--json", *argv)
        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        assert isinstance(payload, dict)
        return payload

    def _mcp(self, name: str, arguments: dict) -> dict:
        response = self.server.handle(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            }
        )
        assert response is not None
        result = response["result"]
        self.assertFalse(result.get("isError"), result)
        return json.loads(result["content"][0]["text"])

    @staticmethod
    def _counts(payload: dict) -> dict[str, int]:
        return {row["table"]: row["rows"] for row in payload["tables"]}

    def test_cli_and_mcp_report_identical_fields(self) -> None:
        cli = self._cli_json("maint", "report")
        mcp = self._mcp("maintenance_report", {})
        self.assertEqual(cli, mcp)
        self.assertEqual(
            set(cli),
            {
                "method",
                "tables",
                "total_bytes",
                "used_bytes",
                "file_bytes",
                "free_bytes",
                "reclaimable_bytes",
                "window_days",
            },
        )

    def test_cli_and_mcp_trim_counts_are_identical(self) -> None:
        cli = self._cli_json("maint", "trim")
        mcp = self._mcp("maintenance_trim", {"apply": False})
        self.assertEqual(cli, mcp)
        self.assertEqual(set(cli), {"tables", "total_rows", "applied"})
        self.assertGreater(self._counts(cli)["task_claims"], 0)

    def test_porcelain_fields_are_stable(self) -> None:
        code, out, err = self._cli("--porcelain", "maint", "report")
        self.assertEqual(code, 0, err)
        rows = [line.split("\t") for line in out.splitlines()]
        self.assertEqual(len(rows[0]), 8)
        self.assertEqual(rows[0][:2], ["maint", "report"])
        self.assertTrue(all(len(row) == 6 for row in rows[1:]))
        self.assertTrue(any(row[0] == "maint-table" for row in rows))
        report = self._cli_json("maint", "report")
        self.assertEqual(rows[0][3], str(report["total_bytes"]))
        self.assertEqual(rows[0][4], str(report["free_bytes"]))
        self.assertEqual(rows[0][5], str(report["reclaimable_bytes"]))
        self.assertEqual(rows[0][6], str(report["file_bytes"]))
        self.assertEqual(rows[0][7], f"{report['window_days']:g}")

        code, out, err = self._cli("--porcelain", "maint", "trim")
        self.assertEqual(code, 0, err)
        trim_rows = [
            line.split("\t") for line in out.splitlines() if line.startswith("maint-trim\t")
        ]
        self.assertTrue(trim_rows)
        self.assertEqual(trim_rows[0][2], "preview")
        self.assertTrue(all(len(row) == 6 for row in trim_rows))

        code, out, err = self._cli("--porcelain", "maint", "vacuum")
        self.assertEqual(code, 0, err)
        vacuum = out.splitlines()[0].split("\t")
        self.assertEqual(vacuum[0], "maint-vacuum")
        self.assertEqual(vacuum[2], "preview")

    def test_archive_and_restore_json_fields_are_stable(self) -> None:
        archive = self._cli_json("maint", "archive")
        self.assertEqual(set(archive), {"plans", "sessions", "applied", "total"})
        self.assertFalse(archive["applied"])
        self.assertGreater(archive["total"], 0)

        self.store.set_status_raw("plan", self.plan.id, Status.DONE)
        self.store.archive_plan(self.plan.id, actor="qa")
        restore = self._cli_json("maint", "restore", "--plan", str(self.plan.id))
        self.assertEqual(set(restore), {"kind", "id", "restored"})
        self.assertTrue(restore["restored"])

    def test_vacuum_json_fields_are_stable(self) -> None:
        payload = self._cli_json("maint", "vacuum")
        self.assertEqual(
            set(payload),
            {
                "before_bytes",
                "after_bytes",
                "before_free_pages",
                "after_free_pages",
                "freed_bytes",
                "applied",
            },
        )
        self.assertFalse(payload["applied"])

    @unittest.skipUnless(MaintenanceScreen is not None, "textual not installed")
    def test_screen_counts_match_cli_and_mcp(self) -> None:
        cli = self._cli_json("maint", "trim")
        expected = self._counts(cli)
        entries = MaintenanceScreen(self.store).load_entries()
        screen: dict[str, int] = {}
        for entry in entries:
            if not entry.label.startswith("trim  "):
                continue
            table, count = entry.label.removeprefix("trim  ").split("·", 1)
            screen[table.strip()] = int(count.strip())
        self.assertEqual(screen, expected)

    def test_busy_database_exits_one_without_a_traceback(self) -> None:
        locker = sqlite3.connect(self.db, isolation_level=None)
        try:
            locker.execute("BEGIN EXCLUSIVE")
            code, _out, err = self._cli("maint", "vacuum")
        finally:
            locker.rollback()
            locker.close()
        self.assertEqual(code, 1)
        self.assertIn("busy", err.lower())
        self.assertNotIn("Traceback", err)

    def test_failed_snapshot_exits_one_without_mutation(self) -> None:
        before = self._counts(self._cli_json("maint", "trim"))
        with mock.patch.object(
            Store, "backup", side_effect=MaintenanceBackupError("snapshot failed")
        ):
            code, _out, err = self._cli("maint", "trim", "--apply")
        self.assertEqual(code, 1)
        self.assertIn("snapshot failed", err)
        self.assertNotIn("Traceback", err)
        after = self._counts(self._cli_json("maint", "trim"))
        self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
