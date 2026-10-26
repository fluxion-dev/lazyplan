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

    def test_tools_and_resources_start_empty(self):
        self.assertEqual(_call(self.server, "tools/list")["result"]["tools"], [])
        self.assertEqual(_call(self.server, "resources/list")["result"]["resources"], [])


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
