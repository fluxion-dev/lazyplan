"""`lpui audit`: JSON shape, strict exit, and no database creation."""

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from home_sandbox import sandbox_home  # noqa: E402

from lazyplan import audit, services, setup  # noqa: E402
from lazyplan.cli import main as lpui_main  # noqa: E402
from lazyplan.models import Status  # noqa: E402
from lazyplan.store import Store  # noqa: E402


class AuditCliCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        self.home.mkdir()
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir()
        self.old_db = os.environ.pop("LAZYPLAN_DB", None)
        self.old_nosetup = os.environ.pop(setup.NO_SETUP_ENV, None)
        self.old_cwd = os.getcwd()
        sandbox_home(self, str(self.home))
        os.chdir(self.repo)

    def tearDown(self):
        os.chdir(self.old_cwd)
        for key, value in (
            ("LAZYPLAN_DB", self.old_db),
            (setup.NO_SETUP_ENV, self.old_nosetup),
        ):
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()

    def _run(self, argv: list[str]) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = lpui_main(argv)
        return code, out.getvalue(), err.getvalue()

    def _seed_gap(self) -> None:
        store = Store(self.home / ".lazyplan/lazyplan.db")
        plan = store.add_plan("P", "what", goal="why")
        milestone = store.add_milestone(plan.id, "M", "desc")
        task = store.add_task(milestone.id, "T", "desc")
        store.add_criteria("task", task.id, "unfinished")
        services.set_status(store, "task", task.id, Status.DONE, actor="t")
        services.set_status(store, "milestone", milestone.id, Status.DONE, actor="t")
        services.set_status(store, "plan", plan.id, Status.DONE, actor="t")

    def test_min_trace_gates_strict_mode(self):
        store = Store(self.home / ".lazyplan/lazyplan.db")
        plan = store.add_plan("P", "what", goal="why")
        store.add_criteria("plan", plan.id, "unproven")
        code, _out, _err = self._run(
            [
                "--db",
                str(store.path),
                "audit",
                "--plan",
                str(plan.id),
                "--strict",
                "--min-trace",
                "0.8",
            ]
        )
        self.assertEqual(code, 2)

    def test_missing_database_reports_empty_without_creating_files(self):
        code, out, _err = self._run(["audit", "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["commits_total"], 0)
        self.assertFalse((self.home / ".lazyplan").exists())

    def test_json_carries_metrics_and_breaches(self):
        self._seed_gap()
        code, out, err = self._run(["audit", "--json"])
        self.assertEqual(code, 0)
        self.assertNotIn("{", err)
        self.assertNotIn("\x1b", err)
        payload = json.loads(out)
        for key in (
            "coverage",
            "median_lag_commits",
            "median_lag_minutes",
            "criteria_gaps",
            "breaches",
        ):
            self.assertIn(key, payload)
        self.assertEqual(payload["criteria_gaps"][0]["text"], "unfinished")

    def test_strict_exits_two_on_gap(self):
        self._seed_gap()
        code, out, _err = self._run(["audit", "--strict", "--json"])
        self.assertEqual(code, 2)
        self.assertTrue(json.loads(out)["breaches"])

    def test_strict_passes_a_clean_plan(self):
        store = Store(self.home / ".lazyplan/lazyplan.db")
        store.add_plan("P", "what", goal="why")
        code, _out, _err = self._run(["audit", "--strict"])
        self.assertEqual(code, 0)

    def test_strict_thresholds_are_configurable(self):
        self._seed_gap()
        code, _out, _err = self._run(["audit", "--strict", "--max-gaps", "5"])
        self.assertEqual(code, 0)

    def test_unknown_plan_is_an_error(self):
        Store(self.home / ".lazyplan/lazyplan.db")
        code, _out, err = self._run(["audit", "--plan", "999"])
        self.assertEqual(code, 1)
        self.assertIn("not found", err)

    def test_corrupt_database_reports_without_traceback(self):
        path = self.home / ".lazyplan/lazyplan.db"
        path.parent.mkdir(parents=True)
        path.write_text("not a database", encoding="utf-8")
        code, _out, err = self._run(["audit", "--json"])
        self.assertEqual(code, 2)
        self.assertIn("cannot read the database", err)
        self.assertNotIn("Traceback", err)


class ThresholdsTest(unittest.TestCase):
    def test_defaults_are_the_documented_ones(self):
        limits = audit.Thresholds()
        self.assertEqual(limits.coverage, 0.8)
        self.assertEqual(limits.lag_commits, 1.0)
        self.assertEqual(limits.gaps, 0)


if __name__ == "__main__":
    unittest.main()
