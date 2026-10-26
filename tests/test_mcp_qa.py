"""End-to-end MCP session over real stdio pipes."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from home_sandbox import sandbox_env  # noqa: E402

from lazyplan.store import Store  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class McpClient:
    """Tiny stdio client for tests."""

    def __init__(self, db: str, read_only: bool = False):
        env = dict(os.environ)
        env["PYTHONPATH"] = os.path.join(ROOT, "src")
        env["LAZYPLAN_NO_SETUP"] = "1"
        sandbox_env(env, os.path.dirname(db))
        args = [
            sys.executable,
            "-m",
            "lazyplan",
            "--db",
            db,
            "--actor",
            "qa",
            "mcp",
        ]
        if read_only:
            args.append("--read-only")
        self.proc = subprocess.Popen(
            args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            cwd=os.path.dirname(db),
        )
        self.next_id = 1

    def send(self, method: str, params: dict | None = None, *, raw: str | None = None) -> dict:
        assert self.proc.stdin is not None and self.proc.stdout is not None
        if raw is None:
            request = {
                "jsonrpc": "2.0",
                "id": self.next_id,
                "method": method,
                "params": params or {},
            }
            self.next_id += 1
            line = json.dumps(request)
        else:
            line = raw
        self.proc.stdin.write(line + "\n")
        self.proc.stdin.flush()
        return json.loads(self.proc.stdout.readline())

    def tool(self, name: str, arguments: dict | None = None) -> dict:
        return self.send("tools/call", {"name": name, "arguments": arguments or {}})["result"]

    def close(self) -> None:
        assert self.proc.stdin is not None
        self.proc.stdin.close()
        self.proc.wait(timeout=30)


class TestMcpEndToEnd(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "qa.db")
        store = Store(self.db)
        plan = store.add_plan("P", "what", goal="why", actor="fixture")
        milestone = store.add_milestone(plan.id, "M", actor="fixture")
        store.add_task(
            milestone.id,
            "T",
            "Commit slice: one.\n\nVerification: pytest.",
            actor="fixture",
        )
        store.add_criteria("plan", plan.id, "Works", actor="fixture")

    def tearDown(self):
        self.tmp.cleanup()

    def test_full_session_reads_writes_resources_and_survives_noise(self):
        client = McpClient(self.db)
        try:
            init = client.send("initialize")["result"]
            self.assertIn("tools", init["capabilities"])
            tools = client.send("tools/list")["result"]["tools"]
            names = {tool["name"] for tool in tools}
            self.assertIn("brief", names)
            self.assertIn("create_task", names)

            shown = json.loads(
                client.tool("show_row", {"kind": "plan", "id": 1})["content"][0]["text"]
            )
            self.assertEqual(shown["plan"]["name"], "P")
            created = client.tool(
                "create_task",
                {"milestone": 1, "title": "MCP task", "desc": "From MCP"},
            )
            task_id = json.loads(created["content"][0]["text"])["id"]
            client.tool("claim_task", {"id": task_id, "ttl": "30m"})
            client.tool("note_add", {"kind": "task", "id": task_id, "text": "handoff"})
            client.tool("block_task", {"id": task_id, "reason": "waiting"})
            client.tool("unblock_task", {"id": task_id})
            client.tool("move_row", {"kind": "task", "id": task_id, "to": "done"})

            brief = client.send("resources/read", {"uri": "lazyplan://brief"})["result"]
            self.assertIn("plans", json.loads(brief["contents"][0]["text"]))
            plan_doc = client.send("resources/read", {"uri": "lazyplan://plan/1"})["result"]
            self.assertIn("plan", json.loads(plan_doc["contents"][0]["text"]))

            malformed = client.send("", raw="not json")
            self.assertEqual(malformed["error"]["code"], -32700)
            self.assertEqual(client.send("ping")["result"], {})
        finally:
            client.close()
        store = Store(self.db)
        self.assertTrue(any(event["actor"] == "qa" for event in store.feed(50)))
        self.assertEqual(store.get_task(task_id).status.value, "done")

    def test_read_only_session_refuses_writes(self):
        client = McpClient(self.db, read_only=True)
        try:
            names = {tool["name"] for tool in client.send("tools/list")["result"]["tools"]}
            self.assertNotIn("create_task", names)
            response = client.send(
                "tools/call",
                {"name": "create_task", "arguments": {"milestone": 1, "title": "Nope"}},
            )
            self.assertIn("error", response)
            self.assertEqual(client.send("ping")["result"], {})
        finally:
            client.close()
        self.assertEqual(len(Store(self.db).list_tasks(1)), 1)


if __name__ == "__main__":
    unittest.main()
