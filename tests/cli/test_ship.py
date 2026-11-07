"""Ship note CLI and MCP surface."""

from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from lazyplan.presentation.cli import main as lpui_main
from lazyplan.store import Store


class ShipCliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "t.db")
        self.store = Store(self.db)
        self.plan = self.store.add_plan("P", "what", goal="why")
        milestone = self.store.add_milestone(self.plan.id, "M")
        self.store.add_task(milestone.id, "Task")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _run(self, *argv: str) -> tuple[int, str, str]:
        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = lpui_main(["--db", self.db, *argv])
        return code, out.getvalue(), err.getvalue()

    def test_markdown_and_json(self) -> None:
        code, out, err = self._run("ship", "--plan", str(self.plan.id))
        self.assertEqual(code, 0, err)
        self.assertIn("## Why", out)
        self.assertIn("## What shipped", out)
        code, out, err = self._run("--json", "ship", "--plan", str(self.plan.id))
        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertEqual(payload["plan"], self.plan.id)
        self.assertIn("## Evidence", payload["markdown"])

    def test_active_plan_and_unknown_plan(self) -> None:
        code, out, err = self._run("ship")
        self.assertEqual(code, 0, err)
        self.assertIn("P1", out)
        code, _out, err = self._run("ship", "--plan", "999")
        self.assertEqual(code, 1)

    def test_porcelain_row(self) -> None:
        code, out, err = self._run("--porcelain", "ship", "--plan", str(self.plan.id))
        self.assertEqual(code, 0, err)
        parts = out.strip().split("\t")
        self.assertEqual(parts[0], "ship")
        self.assertEqual(parts[1], str(self.plan.id))

    def test_max_chars(self) -> None:
        code, out, err = self._run("ship", "--plan", str(self.plan.id), "--max-chars", "200")
        self.assertEqual(code, 0, err)
        self.assertLessEqual(len(out), 200)

    def test_no_database_does_not_create_one(self) -> None:
        missing = os.path.join(self.tmp.name, "missing.db")
        out = io.StringIO()
        with redirect_stdout(out):
            code = lpui_main(["--db", missing, "ship"])
        self.assertEqual(code, 0)
        self.assertIn("no active plans", out.getvalue())
        self.assertFalse(os.path.exists(missing))


if __name__ == "__main__":
    unittest.main()
