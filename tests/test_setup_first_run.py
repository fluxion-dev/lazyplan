"""First run installs the same integrations as an explicit setup."""

import argparse
import io
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from support.home import sandbox_home  # noqa: E402

from lazyplan import setup  # noqa: E402


def make_args(**overrides: object) -> argparse.Namespace:
    values = {
        "db": "",
        "version": False,
        "json": False,
        "yes": False,
        "post_upgrade": False,
        "hooks": None,
        "agents_pointer": None,
        "placement": None,
        "agents": None,
        "skills_dir": None,
        "no_skills": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


class FirstRunCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        self.home.mkdir()
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q", self.repo], check=True)
        self.old_db = os.environ.pop("LAZYPLAN_DB", None)
        sandbox_home(self, str(self.home))

    def tearDown(self):
        if self.old_db is not None:
            os.environ["LAZYPLAN_DB"] = self.old_db
        self.tmp.cleanup()

    def test_first_run_installs_hooks_and_reports_them(self):
        args = make_args(agents="claude")
        err = io.StringIO()
        with redirect_stderr(err):
            setup.ensure("ui", args, self.repo, self.home, "1.0", interactive=False)
        self.assertIn(
            "lpui hook", (self.home / ".claude/settings.json").read_text(encoding="utf-8")
        )
        self.assertTrue(setup.load_state(self.home).hooks)
        self.assertIn("Setup complete", err.getvalue())

    def test_first_run_honors_the_agents_pointer(self):
        args = make_args(agents="claude", agents_pointer=True)
        with redirect_stderr(io.StringIO()):
            setup.ensure("ui", args, self.repo, self.home, "1.0", interactive=False)
        self.assertIn("lazyplan", (self.repo / "AGENTS.md").read_text(encoding="utf-8"))
        self.assertTrue(setup.load_state(self.home).agents_pointer)

    def test_agent_command_stays_quiet(self):
        args = make_args(agents="claude")
        err = io.StringIO()
        with redirect_stderr(err):
            setup.ensure("list", args, self.repo, self.home, "1.0", interactive=False)
        self.assertTrue(setup.load_state(self.home).hooks)
        self.assertNotIn("Setup complete", err.getvalue())

    def test_current_agent_command_skips_the_finding_scan(self):
        args = make_args(agents="claude")
        setup.ensure("list", args, self.repo, self.home, "1.0", interactive=False)
        with mock.patch.object(setup, "detect_findings") as findings:
            setup.ensure("list", args, self.repo, self.home, "1.0", interactive=False)
        findings.assert_not_called()

    def test_json_first_run_never_prompts(self):
        args = make_args(agents="claude", json=True)
        with (
            mock.patch.object(setup.setup_ui, "stdin_tty", return_value=True),
            mock.patch.object(setup.sys.stderr, "isatty", return_value=True),
            mock.patch.object(setup, "run_wizard") as wizard,
            redirect_stderr(io.StringIO()),
        ):
            setup.ensure("ui", args, self.repo, self.home, "1.0")
        wizard.assert_not_called()
        self.assertTrue((self.home / ".claude/settings.json").is_file())

    def test_yes_first_run_never_prompts(self):
        args = make_args(agents="claude", yes=True)
        with (
            mock.patch.object(setup.setup_ui, "stdin_tty", return_value=True),
            mock.patch.object(setup.sys.stderr, "isatty", return_value=True),
            mock.patch.object(setup, "run_wizard") as wizard,
            redirect_stderr(io.StringIO()),
        ):
            setup.ensure("ui", args, self.repo, self.home, "1.0")
        wizard.assert_not_called()

    def test_pointer_rerun_is_idempotent(self):
        db = self.home / ".lazyplan/lazyplan.db"
        db.parent.mkdir(parents=True)
        db.touch()
        setup.install_pointer(self.home, "home", self.repo, db, True)
        result = setup.install_pointer(self.home, "home", self.repo, db, True)
        self.assertEqual(result["status"], "up-to-date")
        self.assertIsNone(result["path"])
        self.assertFalse((self.home / ".lazyplan/backups").exists())

    def test_skipped_hook_write_is_not_recorded_as_installed(self):
        skipped = {"installed": [], "backups": [], "skipped": [{"path": "x", "reason": "nope"}]}
        with mock.patch.object(setup.hook_install, "install", return_value=skipped):
            setup.install_hooks(self.home, ["claude"])
        self.assertFalse(setup.load_state(self.home).hooks)

    def test_wrong_typed_state_falls_back_to_defaults(self):
        path = setup.state_path(self.home)
        path.parent.mkdir(parents=True)
        path.write_text('{"version": "not-a-number"}', encoding="utf-8")
        self.assertEqual(setup.load_state(self.home).version, setup.SETUP_VERSION)

    def test_persistent_findings_do_not_rewrite_setup(self):
        setup.save_state(setup.SetupState(last_version="1.0", placement="home"), self.home)
        finding = setup.Finding(key="k", kind="legacy-dir", path=self.repo / ".plan", detail="x")
        with (
            mock.patch.object(setup, "detect_findings", return_value=[finding]),
            mock.patch.object(setup, "apply_choice") as apply,
        ):
            setup.ensure("list", make_args(), self.repo, self.home, "1.0", interactive=False)
        apply.assert_not_called()

    def test_xdg_fallback_database_is_reported(self):
        xdg = Path(self.tmp.name) / "xdg"
        old = os.environ.get("XDG_DATA_HOME")
        os.environ["XDG_DATA_HOME"] = str(xdg)
        try:
            db = xdg / "lazyplan/lazyplan.db"
            db.parent.mkdir(parents=True)
            from lazyplan.store import Store

            Store(db).add_plan("old")
            findings = setup._legacy_db_findings(self.home)
        finally:
            if old is None:
                os.environ.pop("XDG_DATA_HOME", None)
            else:
                os.environ["XDG_DATA_HOME"] = old
        self.assertTrue(any(f.path == db for f in findings))

    def test_first_run_matrix(self):
        for placement in ("home", "repo"):
            for no_skills in (False, True):
                for json_mode in (False, True):
                    with self.subTest(placement=placement, no_skills=no_skills, json=json_mode):
                        case = Path(self.tmp.name) / f"{placement}-{no_skills}-{json_mode}"
                        home = case / "home"
                        repo = case / "repo"
                        home.mkdir(parents=True)
                        repo.mkdir()
                        subprocess.run(["git", "init", "-q", repo], check=True)
                        args = make_args(
                            placement=placement,
                            no_skills=no_skills,
                            json=json_mode,
                            agents="claude",
                        )
                        with redirect_stderr(io.StringIO()):
                            setup.ensure("ui", args, repo, home, "1.0", interactive=False)
                        home_db = home / ".lazyplan/lazyplan.db"
                        repo_db = repo / ".agents/lazyplan/lazyplan.db"
                        self.assertEqual(home_db.is_file(), placement == "home")
                        self.assertEqual(repo_db.is_file(), placement == "repo")
                        skill_root = repo if placement == "repo" else home
                        skill = skill_root / ".claude/skills/lazyplan/SKILL.md"
                        self.assertEqual(skill.is_file(), not no_skills)
                        self.assertTrue((home / ".claude/settings.json").is_file())


if __name__ == "__main__":
    unittest.main()
