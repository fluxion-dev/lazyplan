"""Agents read lpui through pipes: UTF-8 in and out whatever the locale says.

PYTHONIOENCODING=cp1252 reproduces the Windows pipe default on every OS.
"""

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
TITLE = "Café ✓ relaunch"


class Utf8PipeCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "t.db")
        env = dict(os.environ)
        env["PYTHONPATH"] = os.path.join(ROOT, "src")
        env["LAZYPLAN_NO_SETUP"] = "1"
        env["PYTHONIOENCODING"] = "cp1252"
        env.pop("PYTHONUTF8", None)
        self.env = sandbox_env(env, self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def lpui(self, *argv: str, stdin: bytes = b"") -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            [sys.executable, "-m", "lazyplan", "--db", self.db, *argv],
            input=stdin,
            capture_output=True,
            env=self.env,
            cwd=self.tmp.name,
            timeout=60,
        )

    def test_glyph_output_survives_a_legacy_code_page(self):
        Store(self.db).add_plan(TITLE)
        proc = self.lpui("list", "--tree")
        self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8", "replace"))
        out = proc.stdout.decode("utf-8")
        self.assertIn(TITLE, out)
        self.assertIn("○", out)

    def test_mcp_reads_utf8_requests(self):
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "create_plan", "arguments": {"title": TITLE}},
        }
        line = json.dumps(request, ensure_ascii=False) + "\n"
        proc = self.lpui("mcp", stdin=line.encode("utf-8"))
        self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8", "replace"))
        self.assertEqual([plan.name for plan in Store(self.db).list_plans()], [TITLE])


if __name__ == "__main__":
    unittest.main()
