"""Trace output: criterion → task → commit/PR evidence."""

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

from lazyplan import trace  # noqa: E402
from lazyplan.cli import main as lpui_main  # noqa: E402
from lazyplan.store import Store  # noqa: E402


class TestTrace(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "trace.db")
        store = Store(self.db)
        plan = store.add_plan("P", actor="fixture")
        milestone = store.add_milestone(plan.id, "M", actor="fixture")
        task = store.add_task(milestone.id, "T1", actor="fixture")
        store.add_task(milestone.id, "T2", actor="fixture")
        self.covered = store.add_criteria("plan", plan.id, "Works", actor="fixture")
        self.uncovered = store.add_criteria("plan", plan.id, "Fast", actor="fixture")
        store.relate_criterion(self.covered.id, task.id, actor="fixture")
        store.link_commit(
            "task",
            task.id,
            "a" * 40,
            subject="build it",
            repo_root="/repo",
            actor="fixture",
        )
        store.link_forge(
            "task",
            task.id,
            7,
            provider="github",
            kind="pull",
            url="https://github.com/org/repo/pull/7",
            title="Build it",
            state="open",
            actor="fixture",
        )
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

    def test_trace_plan_walks_evidence(self):
        payload = trace.trace_plan(Store(self.db), 1)
        assert payload is not None
        covered, uncovered = payload["criteria"]
        self.assertEqual(covered["criterion"]["id"], self.covered.id)
        self.assertEqual(covered["tasks"][0]["task"]["id"], 1)
        self.assertEqual(covered["tasks"][0]["commits"][0]["subject"], "build it")
        self.assertEqual(covered["tasks"][0]["forge_links"][0]["number"], 7)
        self.assertEqual(uncovered["tasks"], [])

    def test_trace_criterion(self):
        payload = trace.trace_criterion(Store(self.db), self.covered.id)
        assert payload is not None
        self.assertEqual(payload["criterion"]["text"], "Works")
        self.assertEqual(payload["tasks"][0]["task"]["title"], "T1")

    def test_trace_text_names_missing_evidence(self):
        code, out, err = self._run("trace", "--plan", "1")
        self.assertEqual(code, 0, err)
        self.assertIn("criterion #1 [open] Works", out)
        self.assertIn("T1 T1 (M1)", out)
        self.assertIn("aaaaaaaaaaaa build it", out)
        self.assertIn("PR #7 open Build it", out)
        self.assertIn("criterion #2 [open] Fast", out)
        self.assertIn("(no proving task)", out)

    def test_trace_porcelain(self):
        code, out, err = self._run("--porcelain", "trace", "--plan", "1")
        self.assertEqual(code, 0, err)
        lines = [line.split("\t") for line in out.rstrip("\n").splitlines()]
        for line in lines:
            self.assertEqual(len(line), 6, line)
        self.assertIn(["trace", "1", "proves", "T1", "criterion:1", "task:1"], lines)
        self.assertIn(["trace", "2", "missing", "-", "criterion:2", "-"], lines)
        self.assertTrue(any(line[0] == "commit" and line[1] == "a" * 40 for line in lines))
        self.assertTrue(any(line[0] == "pr" and line[1] == "7" for line in lines))

    def test_trace_json(self):
        code, out, err = self._run("--json", "trace", "--criterion", str(self.covered.id))
        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertEqual(payload["criterion"]["id"], self.covered.id)
        self.assertEqual(payload["tasks"][0]["task"]["id"], 1)

    def test_missing_plan_or_criterion_exits_one(self):
        code, out, err = self._run("trace", "--plan", "99")
        self.assertEqual(code, 1)
        self.assertIn("plan 99", err)
        code, out, err = self._run("trace", "--criterion", "99")
        self.assertEqual(code, 1)
        self.assertIn("criterion 99", err)


if __name__ == "__main__":
    unittest.main()
