"""MCP exposes live agents and keeps legacy history readable."""

from __future__ import annotations

import json
import os
import tempfile
import unittest

from lazyplan.presentation import mcp
from lazyplan.store import Store


class TestAgentMcpTools(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(os.path.join(self.tmp.name, "mcp-agents.db"))
        self.plan = self.store.add_plan("P")
        self.agent = self.store.add_agent(
            "ana",
            host="opencode",
            host_session="host-1",
            agent="builder",
            plan_id=self.plan.id,
            worktree=self.store.checkout_path(),
        )
        self.store.restore_session_history(
            {
                "id": 7,
                "actor": "ana",
                "plan_id": self.plan.id,
                "started_at": 100.0,
                "ended_at": 200.0,
                "summary": "old work",
            }
        )
        self.server = mcp.McpServer(self.store, actor="qa")

    def _tool(self, name: str, arguments: dict | None = None) -> dict:
        response = self.server.handle(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments or {}},
            }
        )
        assert response is not None
        result = response["result"]
        text = result["content"][0]["text"]
        return json.loads(text)

    def test_session_list_keeps_the_legacy_s_id(self) -> None:
        rows = self._tool("session_list")
        self.assertEqual([row["id"] for row in rows], [7])
        self.assertEqual(rows[0]["summary"], "old work")


if __name__ == "__main__":
    unittest.main()
