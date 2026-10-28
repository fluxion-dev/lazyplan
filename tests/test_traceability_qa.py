"""End-to-end traceability: relations, trace, lint, audit, and export/import."""

from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from support.home import sandbox_home  # noqa: E402

from lazyplan import services, trace  # noqa: E402
from lazyplan.cli import main as lpui_main  # noqa: E402
from lazyplan.store import Store  # noqa: E402


def _git_available() -> bool:
    try:
        return subprocess.run(["git", "--version"], capture_output=True, timeout=5).returncode == 0
    except (FileNotFoundError, OSError):
        return False


@unittest.skipUnless(_git_available(), "git CLI required")
class TestTraceabilityQA(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = os.path.join(self.tmp.name, "repo")
        os.makedirs(self.repo)
        subprocess.run(["git", "init", "-q", "-b", "main", self.repo], check=True, timeout=10)
        subprocess.run(
            ["git", "-C", self.repo, "config", "user.email", "t@t.t"], check=True, timeout=10
        )
        subprocess.run(
            ["git", "-C", self.repo, "config", "user.name", "Tester"], check=True, timeout=10
        )
        with open(os.path.join(self.repo, "f.txt"), "w", encoding="utf-8") as fh:
            fh.write("hi\n")
        subprocess.run(["git", "-C", self.repo, "add", "."], check=True, timeout=10)
        subprocess.run(["git", "-C", self.repo, "commit", "-qm", "ship it"], check=True, timeout=10)
        self.db = os.path.join(self.tmp.name, "qa.db")
        store = Store(self.db)
        plan = store.add_plan("P", actor="fixture")
        milestone = store.add_milestone(plan.id, "M", actor="fixture")
        task = store.add_task(
            milestone.id,
            "T",
            "Commit slice: one commit.\n\nVerification: pytest.",
            actor="fixture",
        )
        covered = store.add_criteria("plan", plan.id, "Works", actor="fixture")
        store.add_criteria("plan", plan.id, "Fast", actor="fixture")
        store.relate_criterion(covered.id, task.id, actor="fixture")
        self.old_cwd = os.getcwd()
        self.old_setup = os.environ.get("LAZYPLAN_NO_SETUP")
        sandbox_home(self, self.tmp.name)
        os.environ["LAZYPLAN_NO_SETUP"] = "1"
        os.chdir(self.repo)

    def tearDown(self):
        os.chdir(self.old_cwd)
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
            code = lpui_main(["--db", self.db, "--actor", "qa", *argv])
        return code, out.getvalue(), err.getvalue()

    def _json(self, *argv: str) -> object:
        code, out, err = self._run("--json", *argv)
        self.assertEqual(code, 0, err)
        return json.loads(out)

    def test_trace_evidence_across_text_porcelain_and_json(self):
        self._json("link", "--kind", "task", "--id", "1")
        self._json(
            "pr",
            "link",
            "--kind",
            "task",
            "--id",
            "1",
            "--url",
            "https://github.com/org/repo/pull/7",
        )
        code, text, err = self._run("trace", "--plan", "1")
        self.assertEqual(code, 0, err)
        self.assertIn("criterion #1 [open] Works", text)
        self.assertIn("ship it", text)
        self.assertIn("PR #7", text)
        self.assertIn("criterion #2 [open] Fast", text)
        self.assertIn("(no proving task)", text)

        code, terse, err = self._run("--porcelain", "trace", "--plan", "1")
        self.assertEqual(code, 0, err)
        rows = [line.split("\t") for line in terse.rstrip("\n").splitlines()]
        self.assertIn(["trace", "1", "proves", "T", "criterion:1", "task:1"], rows)
        self.assertIn(["trace", "2", "missing", "-", "criterion:2", "-"], rows)
        self.assertTrue(any(row[0] == "commit" and row[3] == "ship it" for row in rows))
        self.assertTrue(any(row[0] == "pr" and row[1] == "7" for row in rows))

        payload = self._json("trace", "--plan", "1")
        self.assertEqual(payload["criteria"][0]["tasks"][0]["commits"][0]["subject"], "ship it")
        self.assertEqual(payload["criteria"][0]["tasks"][0]["forge_links"][0]["number"], 7)

    def test_lint_and_audit_gate_the_gap(self):
        store = Store(self.db)
        store.add_task(1, "Vague", "TODO: later", actor="fixture")
        code, text, _err = self._run("lint", "--plan", "1")
        self.assertEqual(code, 0)
        self.assertIn("uncovered-criterion", text)
        self.assertIn("missing-commit-slice", text)
        code, _out, _err = self._run("lint", "--plan", "1", "--strict")
        self.assertEqual(code, 2)

        code, audit_text, _err = self._run(
            "audit",
            "--plan",
            "1",
            "--strict",
            "--min-trace",
            "0.8",
            "--min-coverage",
            "0",
            "--max-gaps",
            "10",
        )
        self.assertEqual(code, 2)
        self.assertIn("trace 50% < 80%", audit_text)
        self.assertIn("trace      1/2 criteria", audit_text)

    def test_export_import_preserves_relations_and_trace(self):
        data = services.export_all(Store(self.db))
        other = Store(os.path.join(self.tmp.name, "other.db"))
        counts = services.import_all(other, data, actor="qa")
        self.assertEqual(counts["criterion_links"], 1)
        self.assertEqual([task.id for task in other.criterion_tasks(1)], [1])
        payload = trace.trace_plan(other, 1)
        assert payload is not None
        self.assertEqual(payload["criteria"][0]["tasks"][0]["task"]["id"], 1)


if __name__ == "__main__":
    unittest.main()
