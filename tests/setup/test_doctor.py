"""Doctor reports the layout a real run would use and exits 1 on drift."""

import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from lazyplan.core.entities import Status
from lazyplan.core.policies.worktrees import derive_worktree
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

    def test_doctor_reports_the_hook_probe(self):
        _code, report = self._json(["doctor", "--json"])
        self.assertIn("hook_probe", report)
        self.assertIn(report["hook_probe"]["ok"], (True, False))
        self.assertIn("db", report["hook_probe"])

    def test_findings_exit_one(self):
        plan_dir = self.repo / PLAN_DIR
        plan_dir.mkdir(parents=True)
        Store(repo_plan_db_path(self.repo)).add_plan("P")
        setup.save_state(setup.SetupState(placement="home", last_version="1.0"), self.home)
        code, report = self._json(["doctor", "--json"])
        self.assertEqual(code, 1)
        self.assertTrue(report["findings"])
        self.assertFalse(report["clean"])

    def _git_commit(self) -> None:
        subprocess.run(["git", "-C", str(self.repo), "config", "user.email", "t@example.test"])
        subprocess.run(["git", "-C", str(self.repo), "config", "user.name", "Test"])
        subprocess.run(["git", "-C", str(self.repo), "config", "commit.gpgsign", "false"])
        (self.repo / "README.md").write_text("readme\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.repo), "add", "README.md"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "commit", "-m", "init"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "branch", "-M", "main"], check=True)

    def _worktree_plan(self):
        self._git_commit()
        db = Path(self.tmp.name) / "worktrees.db"
        store = Store(db)
        plan = store.add_plan("Worktrees")
        store.add_repo_link("plan", plan.id, str(self.repo))
        target = derive_worktree(str(self.repo), plan.id, plan.name)
        subprocess.run(
            [
                "git",
                "-C",
                str(self.repo),
                "worktree",
                "add",
                "-b",
                target.branch,
                target.worktree_path,
            ],
            check=True,
        )
        return db, store, plan, target

    def test_clean_worktree_has_no_finding(self):
        db, store, plan, target = self._worktree_plan()
        store.register_plan_worktree(plan.id, str(self.repo), target.worktree_path, target.branch)

        code, report = self._json(["--db", str(db), "doctor", "--json"])

        self.assertEqual(code, 0, report)
        self.assertEqual(report["worktrees"], [])

    def test_doing_plan_without_registration_exits_one(self):
        db, store, plan, _target = self._worktree_plan()
        store.set_status_raw("plan", plan.id, Status.DOING)

        code, report = self._json(["--db", str(db), "doctor", "--json"])

        self.assertEqual(code, 1)
        self.assertEqual(report["worktrees"][0]["state"], "unregistered")
        self.assertIn("without a registered worktree", report["worktrees"][0]["detail"])

    def test_dirty_worktree_exits_one(self):
        db, store, plan, target = self._worktree_plan()
        store.register_plan_worktree(plan.id, str(self.repo), target.worktree_path, target.branch)
        (Path(target.worktree_path) / "scratch.txt").write_text("dirty\n", encoding="utf-8")

        code, report = self._json(["--db", str(db), "doctor", "--json"])

        self.assertEqual(code, 1)
        self.assertEqual(report["worktrees"][0]["state"], "drift")
        self.assertIn("uncommitted changes", report["worktrees"][0]["detail"])

    def test_wrong_branch_and_missing_path_exit_one(self):
        db, store, plan, target = self._worktree_plan()
        store.register_plan_worktree(plan.id, str(self.repo), target.worktree_path, "plan/wrong")

        code, report = self._json(["--db", str(db), "doctor", "--json"])
        self.assertEqual(code, 1)
        self.assertIn("expected", report["worktrees"][0]["detail"])

        shutil.rmtree(target.worktree_path)
        code, report = self._json(["--db", str(db), "doctor", "--json"])
        self.assertEqual(code, 1)
        self.assertEqual(report["worktrees"][0]["state"], "missing-path")

    def test_unlisted_registration_exits_one(self):
        db, store, plan, target = self._worktree_plan()
        store.register_plan_worktree(plan.id, str(self.repo), target.worktree_path, target.branch)

        with mock.patch(
            "lazyplan.services.worktrees.git_worktree_paths",
            return_value={"/somewhere/else"},
        ):
            code, report = self._json(["--db", str(db), "doctor", "--json"])

        self.assertEqual(code, 1)
        self.assertEqual(report["worktrees"][0]["state"], "unlisted")

    def test_human_output_lists_worktree_drift(self):
        db, store, plan, _target = self._worktree_plan()
        store.set_status_raw("plan", plan.id, Status.DOING)
        out = io.StringIO()
        with redirect_stdout(out):
            code = lpui_main(["--db", str(db), "doctor"])
        self.assertEqual(code, 1)
        self.assertIn("worktree:  plan", out.getvalue())

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
