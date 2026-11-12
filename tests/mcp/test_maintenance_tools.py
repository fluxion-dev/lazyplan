"""MCP maintenance tools: report parity and apply-gated writes."""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import time
import unittest
from contextlib import closing
from pathlib import Path

from lazyplan import services
from lazyplan.core.entities import Status
from lazyplan.presentation.mcp.server import McpServer
from lazyplan.store import Store


class TestMcpMaintenance(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "mcp-maint.db")
        self.store = Store(self.db)
        self.plan = self.store.add_plan("Live plan")
        self.milestone = self.store.add_milestone(self.plan.id, "Slice")
        self.task = self.store.add_task(self.milestone.id, "Task")
        self.old = time.time() - 10 * 86400
        with closing(sqlite3.connect(self.db)) as conn:
            conn.execute(
                "INSERT INTO events (ts, actor, kind, action, detail) VALUES (?, 'x', 'x', 'x', 'old')",
                (self.old,),
            )
            conn.commit()
        self.server = McpServer(self.store, actor="qa")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _call(self, name: str, arguments: dict | None = None) -> dict:
        response = self.server.handle(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments or {}},
            }
        )
        assert response is not None
        return response

    def _payload(self, name: str, arguments: dict | None = None) -> dict:
        result = self._call(name, arguments)["result"]
        self.assertFalse(result.get("isError"), result)
        return json.loads(result["content"][0]["text"])

    def _tools(self, server: McpServer | None = None) -> set[str]:
        response = (server or self.server).handle(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
        )
        assert response is not None
        return {item["name"] for item in response["result"]["tools"]}

    def test_report_matches_the_service_fields(self) -> None:
        payload = self._payload("maintenance_report")
        self.assertEqual(payload, services.maintenance.report(self.store).to_dict())

    def test_read_only_server_omits_write_tools(self) -> None:
        names = self._tools()
        self.assertIn("maintenance_report", names)
        self.assertIn("maintenance_trim", names)
        read_only = self._tools(McpServer(self.store, read_only=True))
        self.assertIn("maintenance_report", read_only)
        self.assertNotIn("maintenance_trim", read_only)

    def test_write_tool_requires_the_apply_argument(self) -> None:
        response = self._call("maintenance_trim", {})
        self.assertEqual(response["error"]["code"], -32602)
        self.assertIn("apply", response["error"]["message"])

    def test_apply_false_previews_without_writing(self) -> None:
        payload = self._payload("maintenance_trim", {"apply": False})
        self.assertFalse(payload["applied"])
        with closing(sqlite3.connect(self.db)) as conn:
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM events WHERE detail='old'").fetchone()[0], 1
            )

    def test_apply_true_writes_after_a_snapshot(self) -> None:
        payload = self._payload("maintenance_trim", {"apply": True})
        self.assertTrue(payload["applied"])
        self.assertTrue(list(Path(self.tmp.name).glob("*.bak-*")))
        with closing(sqlite3.connect(self.db)) as conn:
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM events WHERE detail='old'").fetchone()[0], 0
            )

    def test_restore_requires_apply_and_returns_the_row(self) -> None:
        old_plan = self.store.add_plan("Archived")
        services.set_status(self.store, "plan", old_plan.id, Status.DONE)
        self.store.archive_plan(old_plan.id, actor="qa")

        refused = self._call("maintenance_restore", {"plan": old_plan.id, "apply": False})
        self.assertTrue(refused["result"]["isError"])
        still = self.store.get_plan(old_plan.id)
        assert still is not None
        self.assertGreater(still.archived_at, 0)

        restored = self._payload("maintenance_restore", {"plan": old_plan.id, "apply": True})
        self.assertTrue(restored["restored"])
        row = self.store.get_plan(old_plan.id)
        assert row is not None
        self.assertEqual(row.archived_at, 0.0)

    def test_list_plans_hides_archived_plans_by_default(self) -> None:
        self.store.set_status_raw("plan", self.plan.id, Status.DONE)
        self.store.archive_plan(self.plan.id, actor="qa")
        payload = self._payload("list_plans")
        self.assertEqual(payload, [])
        row = self.store.get_plan(self.plan.id)
        assert row is not None
        self.assertGreater(row.archived_at, 0)


if __name__ == "__main__":
    unittest.main()
