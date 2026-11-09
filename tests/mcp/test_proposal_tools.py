"""MCP proposal tools stage changes without writing plan rows."""

from __future__ import annotations

import json
import os
import tempfile
import unittest

from lazyplan.presentation import mcp
from lazyplan.store import Store


class TestProposalTools(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(os.path.join(self.tmp.name, "mcp.db"))
        self.plan = self.store.add_plan("P", "what", goal="why", actor="fixture")
        self.milestone = self.store.add_milestone(self.plan.id, "M", actor="fixture")
        self.server = mcp.McpServer(self.store, actor="agent")

    def tearDown(self) -> None:
        self.tmp.cleanup()

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
        return response["result"]

    def test_tools_are_discoverable_write_tools(self) -> None:
        response = self.server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        assert response is not None
        tools = {tool["name"]: tool for tool in response["result"]["tools"]}
        for name in ("propose_plan", "propose_edit", "propose_task", "proposal_list"):
            self.assertIn(name, tools)
        self.assertFalse(tools["propose_plan"]["annotations"]["readOnlyHint"])

    def test_propose_plan_stages_without_creating_rows(self) -> None:
        document = {
            "plan": {"key": "p1", "title": "Draft", "why": "why", "what": "what"},
            "milestones": [],
        }
        result = self._tool(
            "propose_plan",
            {"title": "Draft", "document": document, "summary": "review me"},
        )
        self.assertFalse(result.get("isError"))
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual(payload["proposal"]["status"], "pending")
        self.assertEqual(self.store.counts()["plans"], 1)
        self.assertEqual(len(self.store.list_proposals()), 1)

    def test_propose_edit_and_task_stage_rows(self) -> None:
        edit = self._tool(
            "propose_edit",
            {"kind": "plan", "id": self.plan.id, "title": "New", "reason": "agent"},
        )
        self.assertFalse(edit.get("isError"))
        task = self._tool(
            "propose_task",
            {"milestone": self.milestone.id, "title": "T", "desc": "d"},
        )
        self.assertFalse(task.get("isError"))
        self.assertEqual(self.store.get_plan(self.plan.id).name, "P")
        self.assertEqual(len(self.store.list_tasks(self.milestone.id)), 0)
        self.assertEqual(len(self.store.list_proposals()), 2)

    def test_proposal_mode_hides_structural_writes(self) -> None:
        server = mcp.McpServer(self.store, actor="agent", proposal_only=True)
        response = server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        assert response is not None
        names = {tool["name"] for tool in response["result"]["tools"]}
        self.assertIn("propose_plan", names)
        self.assertIn("note_add", names)
        self.assertNotIn("create_plan", names)
        self.assertNotIn("move_row", names)
        response = server.handle(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "create_plan", "arguments": {"title": "X"}},
            }
        )
        assert response is not None
        self.assertEqual(response["error"]["code"], -32601)

    def test_unknown_row_is_rejected(self) -> None:
        result = self._tool("propose_edit", {"kind": "plan", "id": 999, "title": "X"})
        self.assertTrue(result.get("isError"))


if __name__ == "__main__":
    unittest.main()
