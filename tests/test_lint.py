"""Plan lint rules, porcelain rows, and strict exit codes."""

from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from home_sandbox import sandbox_home  # noqa: E402

from lazyplan import lint, services  # noqa: E402
from lazyplan.cli import main as lpui_main  # noqa: E402
from lazyplan.models import Status  # noqa: E402
from lazyplan.store import Store  # noqa: E402


class TestLint(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "lint.db")
        store = Store(self.db)
        plan = store.add_plan("P", actor="fixture")
        milestone = store.add_milestone(plan.id, "M", actor="fixture")
        task = store.add_task(
            milestone.id,
            "T",
            "Commit slice: one commit.\n\nVerification: pytest.",
            actor="fixture",
        )
        criterion = store.add_criteria("plan", plan.id, "Works", actor="fixture")
        store.relate_criterion(criterion.id, task.id, actor="fixture")
        self.store = store
        self.old_setup = os.environ.get("LAZYPLAN_NO_SETUP")
        sandbox_home(self, self.tmp.name)
        os.environ["LAZYPLAN_NO_SETUP"] = "1"

    def tearDown(self):
        for key, value in (("LAZYPLAN_NO_SETUP", self.old_setup),):
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()

    def _run(self, *argv: str) -> tuple[int, str, str]:
        out = io.StringIO()
        err = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = lpui_main(["--db", self.db, "--actor", "alice", *argv])
        return code, out.getvalue(), err.getvalue()

    def test_clean_plan_has_no_findings(self):
        self.assertEqual(lint.lint_plan(self.store, 1), [])

    def test_uncovered_criterion(self):
        self.store.add_criteria("plan", 1, "Fast", actor="fixture")
        findings = lint.lint_plan(self.store, 1)
        assert findings is not None
        self.assertIn("uncovered-criterion", [finding.rule for finding in findings])

    def test_missing_slice_verification_and_placeholder(self):
        task = self.store.add_task(1, "Vague", "TODO: something", actor="fixture")
        findings = lint.lint_plan(self.store, 1)
        assert findings is not None
        rules = {finding.rule for finding in findings if finding.obj_id == task.id}
        self.assertIn("missing-commit-slice", rules)
        self.assertIn("missing-verification", rules)
        self.assertIn("placeholder-text", rules)

    def test_done_rows_with_open_criteria(self):
        criterion = self.store.add_criteria("task", 1, "Open", actor="fixture")
        services.set_status(self.store, "task", 1, Status.DONE, actor="fixture")
        services.set_status(self.store, "plan", 1, Status.DONE, actor="fixture")
        findings = lint.lint_plan(self.store, 1)
        assert findings is not None
        self.assertIn(
            "done-with-open-criteria",
            [finding.rule for finding in findings],
        )
        self.assertTrue(criterion.done is False)

    def test_cli_text_and_strict_exit(self):
        self.store.add_criteria("plan", 1, "Fast", actor="fixture")
        code, out, err = self._run("lint", "--plan", "1")
        self.assertEqual(code, 0, err)
        self.assertIn("uncovered-criterion", out)
        code, out, err = self._run("lint", "--plan", "1", "--strict")
        self.assertEqual(code, 2)

    def test_cli_porcelain_and_json(self):
        self.store.add_criteria("plan", 1, "Fast", actor="fixture")
        code, out, err = self._run("--porcelain", "lint", "--plan", "1")
        self.assertEqual(code, 0, err)
        row = out.rstrip("\n").split("\t")
        self.assertEqual(row[:3], ["lint", "uncovered-criterion", "error"])
        self.assertEqual(row[4], "criterion:2")
        code, out, err = self._run("--json", "lint", "--plan", "1")
        payload = json.loads(out)
        self.assertEqual(payload[0]["rule"], "uncovered-criterion")

    def test_missing_plan_exits_one(self):
        code, out, err = self._run("lint", "--plan", "99")
        self.assertEqual(code, 1)
        self.assertIn("plan 99", err)


if __name__ == "__main__":
    unittest.main()
