"""Doctor reports the layout a real run would use and exits 1 on drift."""

import io
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from lazyplan.infrastructure.repo import PLAN_DIR, repo_plan_db_path
from lazyplan.presentation import setup
from lazyplan.presentation.cli import main as lpui_main
from lazyplan.store import Store
from tests.support.home import sandbox_home


class DoctorCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        self.home.mkdir()
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q", self.repo], check=True)
        self.old_xdg = os.environ.get("XDG_DATA_HOME")
        self.old_db = os.environ.pop("LAZYPLAN_DB", None)
        sandbox_home(self, str(self.home))
        os.environ["XDG_DATA_HOME"] = str(Path(self.tmp.name) / "xdg")
        self.old_cwd = os.getcwd()
        os.chdir(self.repo)

    def tearDown(self):
        os.chdir(self.old_cwd)
        if self.old_xdg is None:
            os.environ.pop("XDG_DATA_HOME", None)
        else:
            os.environ["XDG_DATA_HOME"] = self.old_xdg
        if self.old_db is not None:
            os.environ["LAZYPLAN_DB"] = self.old_db
        self.tmp.cleanup()

    def _json(self, argv):
        out = io.StringIO()
        with redirect_stdout(out):
            code = lpui_main(argv)
        return code, json.loads(out.getvalue())

    def testexplicit_db_is_the_reported_database(self):
        db = Path(self.tmp.name) / "elsewhere/lazyplan.db"
        db.parent.mkdir(parents=True)
        Store(db).add_plan("P")
        code, report = self._json(["--db", str(db), "doctor", "--json"])
        self.assertEqual(report["expected"]["db"], str(db))
        self.assertEqual(code, 0, report)

    def test_setup_reports_strict_mode(self):
        self.assertEqual(lpui_main(["setup", "--yes", "--agents", "claude", "--json"]), 0)
        code, report = self._json(["doctor", "--json"])
        self.assertEqual(report["hooks"]["mode"], "strict")
        self.assertEqual(code, 0, report)

    def test_findings_exit_one(self):
        plan_dir = self.repo / PLAN_DIR
        plan_dir.mkdir(parents=True)
        Store(repo_plan_db_path(self.repo)).add_plan("P")
        setup.save_state(setup.SetupState(placement="home", last_version="1.0"), self.home)
        code, report = self._json(["doctor", "--json"])
        self.assertEqual(code, 1)
        self.assertTrue(report["findings"])
        self.assertFalse(report["clean"])

    def test_human_output_lists_skill_paths(self):
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(lpui_main(["setup", "--yes", "--agents", "claude", "--json"]), 0)
        out = io.StringIO()
        with redirect_stdout(out):
            lpui_main(["doctor"])
        self.assertIn("skill:", out.getvalue())
        self.assertIn("hooks:", out.getvalue())
        self.assertNotIn("pending:", out.getvalue())

    def test_pending_integrations_exit_one_and_are_named(self):
        setup.save_state(
            setup.SetupState(placement="home", agents=["claude"], last_version="0.0.0"),
            self.home,
        )
        code, report = self._json(["doctor", "--json"])
        self.assertEqual(code, 1)
        pending = report["pending_integrations"]
        self.assertTrue(pending)
        self.assertTrue(any(item["id"] == "hook:claude:session-start" for item in pending))
        self.assertFalse(report["clean"])

    def test_pending_integrations_appear_in_human_output(self):
        setup.save_state(
            setup.SetupState(placement="home", agents=["claude"], last_version="0.0.0"),
            self.home,
        )
        out = io.StringIO()
        with redirect_stdout(out):
            lpui_main(["doctor"])
        self.assertIn("pending:", out.getvalue())
        self.assertIn("hook:claude:session-start", out.getvalue())


if __name__ == "__main__":
    unittest.main()
