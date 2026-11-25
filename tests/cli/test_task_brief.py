"""Task brief CLI: fresh-session text, budget, JSON, and refusal."""

from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from lazyplan.presentation.cli import main as lpui_main
from lazyplan.store import Store


class TaskBriefCliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "t.db")
        self.store = Store(self.db)
        self.plan = self.store.add_plan("Plan", "the what", goal="the why")
        self.milestone = self.store.add_milestone(
            self.plan.id,
            "Milestone",
            "Outcome: value.\n\nScope: in.\n\nInputs: none.\n\nSlices: one.",
        )
        self.task = self.store.add_task(
            self.milestone.id,
            "Current task",
            (
                "Approach: Change the scouted path.\n\n"
                "Touch: src/app.py\n\n"
                "Inputs: none.\n\n"
                "Commit: One slice.\n\n"
                "Verify: pytest.\n\n"
                "Guardrails: Keep unrelated behavior."
            ),
            role="qa",
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _run(self, *argv: str) -> tuple[int, str, str]:
        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = lpui_main(["--db", self.db, *argv])
        return code, out.getvalue(), err.getvalue()

    def test_prints_a_fresh_session_brief(self) -> None:
        code, out, err = self._run("task", "brief", "--id", str(self.task.id))
        self.assertEqual(code, 0, err)
        self.assertIn("Start a new session for this task", out)
        self.assertIn("Session budget:", out)
        self.assertIn("## Task T1: Current task", out)
        self.assertIn("src/app.py", out)

    def test_json_reports_the_budget(self) -> None:
        code, out, err = self._run("--json", "task", "brief", "--id", str(self.task.id))
        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertTrue(payload["fits"])
        self.assertEqual(payload["window"], 200_000)
        self.assertEqual(payload["budget"], 50_000)
        self.assertIn("Start a new session", payload["text"])

    def test_porcelain_row(self) -> None:
        code, out, err = self._run("--porcelain", "task", "brief", "--id", str(self.task.id))
        self.assertEqual(code, 0, err)
        row = out.rstrip("\n").split("\t")
        self.assertEqual(row[:3], ["brief", "1", "ok"])
        self.assertEqual(row[4], "task:1")

    def test_host_window_override(self) -> None:
        profile = os.path.join(self.tmp.name, "agents.json")
        with open(profile, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "schema": 2,
                    "context": {"standard": {"claude": 32_000}},
                    "profiles": {},
                },
                handle,
            )
        code, out, err = self._run(
            "--json", "task", "brief", "--id", str(self.task.id), "--host", "claude"
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["window"], 32_000)

    def test_oversize_brief_is_refused_after_printing_it(self) -> None:
        self.store.update_task(self.task.id, description="x" * 6000)
        code, out, err = self._run(
            "task", "brief", "--id", str(self.task.id), "--context-window", "1000"
        )
        self.assertEqual(code, 2)
        self.assertIn("# Fresh session for T1", out)
        self.assertIn("fresh brief uses", err)

    def test_missing_task_is_named(self) -> None:
        code, _out, err = self._run("task", "brief", "--id", "999")
        self.assertEqual(code, 1)
        self.assertIn("task 999", err)


if __name__ == "__main__":
    unittest.main()
