"""MCP transport: JSON-RPC lifecycle, errors, and stdout discipline."""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from lazyplan import mcp  # noqa: E402
from lazyplan.store import Store  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _call(server: mcp.McpServer, method: str, params: dict | None = None, id_: int = 1) -> dict:
    response = server.handle(
        {"jsonrpc": "2.0", "id": id_, "method": method, "params": params or {}}
    )
    assert response is not None
    return response


class TestMcpTransport(unittest.TestCase):
    def setUp(self):
        self.server = mcp.McpServer(None)

    def test_initialize_advertises_capabilities(self):
        result = _call(self.server, "initialize")["result"]
        self.assertEqual(result["protocolVersion"], mcp.PROTOCOL_VERSION)
        self.assertIn("tools", result["capabilities"])
        self.assertIn("resources", result["capabilities"])

    def test_ping(self):
        self.assertEqual(_call(self.server, "ping")["result"], {})

    def test_unknown_method_is_structured(self):
        response = _call(self.server, "nope")
        self.assertEqual(response["error"]["code"], -32601)

    def test_notification_has_no_response(self):
        self.assertIsNone(
            self.server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"})
        )

    def test_loop_survives_parse_and_internal_errors(self):
        stdin = io.StringIO(
            "not json\n" + json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"}) + "\n"
        )
        stdout = io.StringIO()
        self.server.serve(stdin, stdout)
        lines = [json.loads(line) for line in stdout.getvalue().splitlines()]
        self.assertEqual(lines[0]["error"]["code"], -32700)
        self.assertEqual(lines[1]["result"], {})

    def test_tools_and_resources_are_discoverable(self):
        self.assertTrue(_call(self.server, "tools/list")["result"]["tools"])
        self.assertTrue(_call(self.server, "resources/list")["result"]["resources"])


class TestMcpReadTools(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        store = Store(os.path.join(self.tmp.name, "mcp.db"))
        plan = store.add_plan("P", "what", goal="why", actor="fixture")
        milestone = store.add_milestone(plan.id, "M", actor="fixture")
        task = store.add_task(
            milestone.id,
            "T",
            "Commit slice: one.\n\nVerification: pytest.",
            actor="fixture",
        )
        criterion = store.add_criteria("plan", plan.id, "Works", actor="fixture")
        store.relate_criterion(criterion.id, task.id, actor="fixture")
        store.claim_task(task.id, "alice", 300)
        self.store = store
        self.server = mcp.McpServer(store, actor="qa")

    def tearDown(self):
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

    def test_tools_list_has_read_surface(self):
        names = {
            tool["name"]
            for tool in self.server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})[
                "result"
            ]["tools"]
        }
        self.assertEqual(
            names,
            {"brief", "list_plans", "show_row", "claims", "audit", "trace", "lint", "info"},
        )

    def test_read_tools_return_json(self):
        result = self._tool("show_row", {"kind": "task", "id": 1})
        self.assertFalse(result.get("isError"))
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual(payload["task"]["title"], "T")
        brief = json.loads(self._tool("brief", {"plan": 1})["content"][0]["text"])
        self.assertEqual(brief["active"], 1)
        claims = json.loads(self._tool("claims")["content"][0]["text"])
        self.assertEqual(claims[0]["actor"], "alice")
        info = json.loads(self._tool("info")["content"][0]["text"])
        self.assertEqual(info["counts"]["plans"], 1)
        trace = json.loads(self._tool("trace", {"plan": 1})["content"][0]["text"])
        self.assertEqual(trace["criteria"][0]["tasks"][0]["task"]["id"], 1)
        lint = json.loads(self._tool("lint", {"plan": 1})["content"][0]["text"])
        self.assertEqual(lint, [])

    def test_missing_rows_are_tool_errors(self):
        result = self._tool("show_row", {"kind": "task", "id": 99})
        self.assertTrue(result["isError"])
        self.assertIn("not found", result["content"][0]["text"])
        result = self._tool("trace", {})
        self.assertTrue(result["isError"])

    def test_resources_read_brief_and_plan(self):
        for uri, key in (("lazyplan://brief", "plans"), ("lazyplan://plan/1", "plan")):
            response = self.server.handle(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "resources/read",
                    "params": {"uri": uri},
                }
            )
            assert response is not None
            content = response["result"]["contents"][0]
            self.assertEqual(content["uri"], uri)
            self.assertIn(key, json.loads(content["text"]))

    def test_missing_resource_is_an_error(self):
        response = self.server.handle(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "resources/read",
                "params": {"uri": "lazyplan://plan/99"},
            }
        )
        assert response is not None
        self.assertEqual(response["error"]["code"], -32002)

    def test_missing_database_read_is_an_error(self):
        server = mcp.McpServer(None)
        result = server.handle(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "info", "arguments": {}},
            }
        )["result"]
        self.assertTrue(result["isError"])
        self.assertIn("no database", result["content"][0]["text"])


class TestMcpCli(unittest.TestCase):
    def test_read_only_does_not_create_a_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "missing.db")
            env = dict(os.environ)
            env["PYTHONPATH"] = os.path.join(ROOT, "src")
            env["LAZYPLAN_NO_SETUP"] = "1"
            env["HOME"] = tmp
            proc = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "lazyplan",
                    "--db",
                    db,
                    "--actor",
                    "qa",
                    "mcp",
                    "--read-only",
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
                cwd=tmp,
            )
            assert proc.stdin is not None and proc.stdout is not None
            proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize"}) + "\n")
            proc.stdin.flush()
            line = proc.stdout.readline()
            proc.stdin.close()
            proc.wait(timeout=30)
            self.assertEqual(json.loads(line)["id"], 1)
            self.assertFalse(os.path.exists(db), "read-only MCP created a database")


if __name__ == "__main__":
    unittest.main()
