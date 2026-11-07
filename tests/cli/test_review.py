"""Review CLI: Markdown, JSON, active-plan fallback, and read-only behavior."""

from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from lazyplan.presentation.cli import main as lpui_main
from lazyplan.store import Store


class ReviewCliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "t.db")
        self.store = Store(self.db)
        self.plan = self.store.add_plan("Plan", "What", goal="Why")
        self.milestone = self.store.add_milestone(self.plan.id, "M")
        self.task = self.store.add_task(
            self.milestone.id,
            "T",
            "Approach: do it.\n\nCommit: one slice.\n\nVerify: pytest.",
        )
        criterion = self.store.add_criteria("plan", self.plan.id, "Works")
        self.store.relate_criterion(criterion.id, self.task.id)
        self.store.add_question(self.plan.id, "Which host?")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _run(self, *argv: str) -> tuple[int, str, str]:
        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = lpui_main(["--db", self.db, *argv])
        return code, out.getvalue(), err.getvalue()

    def test_json_packet_and_active_plan_fallback(self) -> None:
        code, out, err = self._run("--json", "review")
        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertEqual(payload["plan"], self.plan.id)
        self.assertIn("# P1 — Plan", payload["markdown"])
        self.assertEqual(payload["payload"]["questions"][0]["text"], "Which host?")

    def test_text_packet(self) -> None:
        code, out, err = self._run("review", "--plan", str(self.plan.id))
        self.assertEqual(code, 0, err)
        self.assertIn("# P1 — Plan", out)
        self.assertIn("## Acceptance criteria", out)
        self.assertIn("Which host?", out)

    def test_max_chars(self) -> None:
        code, out, err = self._run(
            "--json", "review", "--plan", str(self.plan.id), "--max-chars", "200"
        )
        self.assertEqual(code, 0, err)
        self.assertLessEqual(len(json.loads(out)["markdown"]), 200)

    def test_porcelain_summary(self) -> None:
        code, out, err = self._run("--porcelain", "review", "--plan", str(self.plan.id))
        self.assertEqual(code, 0, err)
        row = out.split("\t")
        self.assertEqual(row[0], "review")
        self.assertEqual(row[1], str(self.plan.id))

    def test_unknown_plan_and_empty_store(self) -> None:
        code, _out, err = self._run("review", "--plan", "999")
        self.assertEqual(code, 1)
        self.assertIn("plan 999", err)
        empty = os.path.join(self.tmp.name, "empty.db")
        Store(empty)
        out = io.StringIO()
        with redirect_stdout(out):
            code = lpui_main(["--db", empty, "review"])
        self.assertEqual(code, 0)
        self.assertIn("no active plans", out.getvalue())

    def test_missing_database_does_not_create_one(self):
        missing = os.path.join(self.tmp.name, "missing.db")
        out = io.StringIO()
        with redirect_stdout(out):
            code = lpui_main(["--db", missing, "review"])
        self.assertEqual(code, 0)
        self.assertIn("no active plans", out.getvalue())
        self.assertFalse(os.path.exists(missing))


if __name__ == "__main__":
    unittest.main()
