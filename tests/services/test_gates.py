"""Completion gates: cached PR/check evidence and overrides."""

from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import tempfile
import unittest

from lazyplan import services
from lazyplan.cli import main as lpui_main
from lazyplan.models import Status
from lazyplan.store import Store


def _git_available() -> bool:
    return subprocess.run(["git", "--version"], capture_output=True).returncode == 0


@unittest.skipUnless(_git_available(), "git CLI required")
class TestCompletionGates(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = os.path.join(self.tmp.name, "repo")
        os.makedirs(self.repo)
        subprocess.run(["git", "init", "-q", "-b", "main", self.repo], check=True)
        subprocess.run(["git", "-C", self.repo, "config", "user.email", "t@t.t"], check=True)
        subprocess.run(["git", "-C", self.repo, "config", "user.name", "T"], check=True)
        with open(os.path.join(self.repo, "f"), "w", encoding="utf-8") as fh:
            fh.write("x")
        subprocess.run(["git", "-C", self.repo, "add", "."], check=True)
        subprocess.run(["git", "-C", self.repo, "commit", "-qm", "one"], check=True)
        self.db = os.path.join(self.tmp.name, "gates.db")
        self.store = Store(self.db)
        plan = self.store.add_plan("P", actor="fixture")
        milestone = self.store.add_milestone(plan.id, "M", actor="fixture")
        self.task = self.store.add_task(
            milestone.id, "T", "Commit slice. Verification.", actor="fixture"
        )
        self.old_cwd = os.getcwd()
        os.chdir(self.repo)
        services.start_task(self.store, self.task.id, actor="fixture")

    def tearDown(self):
        os.chdir(self.old_cwd)
        self.tmp.cleanup()

    def _pr(self, checks: str) -> None:
        self.store.link_forge(
            "task",
            self.task.id,
            7,
            checks=checks,
            state="open",
            title="PR",
            actor="fixture",
        )

    def test_missing_pr_fails(self):
        with self.assertRaises(services.GateError):
            services.finish_task(self.store, self.task.id, require_pr=True, actor="fixture")
        self.assertEqual(self.store.get_task(self.task.id).status, Status.DOING)

    def test_failing_and_pending_checks_fail(self):
        self._pr("fail")
        with self.assertRaises(services.GateError):
            services.finish_task(self.store, self.task.id, require_checks=True, actor="fixture")
        self.assertEqual(self.store.get_task(self.task.id).status, Status.DOING)
        # replace the cached state to pending
        with self.store._connect() as conn:
            conn.execute(
                "UPDATE forge_links SET checks='pending' WHERE parent_id=?", (self.task.id,)
            )
        with self.assertRaises(services.GateError):
            services.finish_task(self.store, self.task.id, require_checks=True, actor="fixture")

    def test_pass_allows_completion(self):
        self._pr("pass")
        result = services.finish_task(
            self.store, self.task.id, require_pr=True, require_checks=True, actor="fixture"
        )
        self.assertTrue(result["done"])
        self.assertEqual(result["gate"]["state"], "pass")
        self.assertEqual(self.store.get_task(self.task.id).status, Status.DONE)

    def test_override_records_reason(self):
        self._pr("fail")
        result = services.finish_task(
            self.store,
            self.task.id,
            require_checks=True,
            override="known flaky runner",
            actor="fixture",
        )
        self.assertTrue(result["done"])
        notes = self.store.list_notes("task", self.task.id)
        self.assertIn("known flaky runner", notes[-1].text)

    def _run(self, *argv: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = lpui_main(["--db", self.db, "--actor", "fixture", *argv])
        return code, out.getvalue(), err.getvalue()

    def test_gate_state_in_reads(self):
        self._pr("pass")
        code, out, err = self._run("task", "show", "--id", str(self.task.id))
        self.assertEqual(code, 0, err)
        self.assertIn("gate: pass", out)
        code, out, err = self._run("--porcelain", "task", "show", "--id", str(self.task.id))
        self.assertIn("gate\tpass\tpass\t1 PRs", out)
        code, out, err = self._run("--json", "brief", "--plan", "1")
        payload = json.loads(out)
        tasks = payload["plans"][0]["doing"]
        self.assertEqual(tasks[0]["gate"]["state"], "pass")

    def test_branch_collision_and_restart(self):
        second = self.store.add_task(
            self.store.get_task(self.task.id).milestone_id,
            "T2",
            "Commit slice. Verification.",
            actor="fixture",
        )
        with self.assertRaises(ValueError) as caught:
            services.start_task(self.store, second.id, actor="fixture")
        self.assertIn(f"task #{self.task.id}", str(caught.exception))
        services.start_task(self.store, self.task.id, actor="fixture")

    def test_cli_require_pr_failure_and_override(self):
        code, out, err = self._run("task", "finish", "--id", str(self.task.id), "--require-pr")
        self.assertEqual(code, 2)
        self.assertIn("no linked pull request", err)
        self.assertEqual(self.store.get_task(self.task.id).status, Status.DOING)
        self._pr("fail")
        code, out, err = self._run(
            "task",
            "finish",
            "--id",
            str(self.task.id),
            "--require-checks",
            "--override",
            "known flaky",
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(self.store.get_task(self.task.id).status, Status.DONE)
        self.assertIn("known flaky", self.store.list_notes("task", self.task.id)[-1].text)

    def test_gate_state(self):
        self.assertEqual(services.gate_state(self.store, self.task.id)["state"], "missing")
        self._pr("pass")
        self.assertEqual(services.gate_state(self.store, self.task.id)["checks"], "pass")


if __name__ == "__main__":
    unittest.main()
