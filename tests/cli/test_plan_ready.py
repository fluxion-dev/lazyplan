"""Plan-ready CLI: checks, JSON, porcelain, and exit codes."""

from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from lazyplan.presentation.cli import main as lpui_main
from lazyplan.store import Store


class PlanReadyCliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "t.db")
        self.store = Store(self.db)
        self.plan = self.store.add_plan("P")
        self.milestone = self.store.add_milestone(self.plan.id, "M")
        self.task = self.store.add_task(
            self.milestone.id,
            "T",
            "Approach: do it.\n\nCommit: one slice.\n\nVerify: pytest.",
        )
        criterion = self.store.add_criteria("plan", self.plan.id, "Works")
        self.store.relate_criterion(criterion.id, self.task.id)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _run(self, *argv: str) -> tuple[int, str, str]:
        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = lpui_main(["--db", self.db, *argv])
        return code, out.getvalue(), err.getvalue()

    def test_clean_plan_is_ready(self) -> None:
        code, out, err = self._run("plan", "ready", "--id", str(self.plan.id))
        self.assertEqual(code, 0, err)
        self.assertIn("P1 ready", out)
        self.assertIn("lint", out)
        self.assertIn("coverage", out)
        self.assertIn("questions", out)

    def test_open_question_blocks(self) -> None:
        self.store.add_question(self.plan.id, "Which host?")
        code, out, err = self._run("plan", "ready", "--id", str(self.plan.id))
        self.assertEqual(code, 1, err)
        self.assertIn("not ready", out)
        self.assertIn("Which host?", out)
        code, out, err = self._run("--json", "plan", "ready", "--id", str(self.plan.id))
        self.assertEqual(code, 1, err)
        payload = json.loads(out)
        self.assertFalse(payload["ready"])
        questions = next(check for check in payload["checks"] if check["id"] == "questions")
        self.assertFalse(questions["ok"])

    def test_porcelain_rows(self) -> None:
        code, out, err = self._run("--porcelain", "plan", "ready", "--id", str(self.plan.id))
        self.assertEqual(code, 0, err)
        rows = [line.split("\t") for line in out.splitlines()]
        self.assertEqual([row[0] for row in rows], ["check", "check", "check"])
        self.assertEqual([row[2] for row in rows], ["pass", "pass", "pass"])

    def test_unknown_plan_and_missing_database(self) -> None:
        code, _out, err = self._run("plan", "ready", "--id", "999")
        self.assertEqual(code, 2)
        self.assertIn("plan 999", err)
        missing = os.path.join(self.tmp.name, "missing.db")
        out = io.StringIO()
        with redirect_stdout(out):
            code = lpui_main(["--db", missing, "plan", "ready", "--id", "1"])
        self.assertEqual(code, 2)
        self.assertFalse(os.path.exists(missing))


if __name__ == "__main__":
    unittest.main()
