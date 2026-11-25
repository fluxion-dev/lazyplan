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
        self.plan = self.store.add_plan("P", worktree_required=False)
        self.milestone = self.store.add_milestone(
            self.plan.id,
            "M",
            (
                "Outcome: As a user, I want the change, so that the outcome is visible.\n\n"
                "Scope: In scope: the reviewed definition. Out of scope: unrelated work.\n\n"
                "Inputs: The approved definition and the scouted code path.\n\n"
                "Slices: Implement and verify in separate green commits."
            ),
        )
        self.task = self.store.add_task(
            self.milestone.id,
            "T",
            (
                "Approach: Change the scouted code path and keep the reviewed behavior.\n\n"
                "Touch: src/app.py, tests/test_app.py\n\n"
                "Inputs: The approved definition; none beyond the plan scope.\n\n"
                "Commit: One implementation slice.\n\n"
                "Verify: The relevant test suite passes.\n\n"
                "Guardrails: Keep behavior outside the reviewed scope unchanged."
            ),
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
        self.assertEqual([row[0] for row in rows], ["check"] * 5)
        self.assertEqual([row[2] for row in rows], ["pass"] * 5)

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
