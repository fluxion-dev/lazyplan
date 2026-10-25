"""Lifecycle scenario: first run, rerun, switch placement, doctor, and upgrade."""

import io
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from lazyplan import setup  # noqa: E402
from lazyplan.cli import main as lpui_main  # noqa: E402


class LifecycleCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        self.home.mkdir()
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q", self.repo], check=True)
        self.old_home = os.environ.get("HOME")
        self.old_db = os.environ.pop("LAZYPLAN_DB", None)
        self.old_xdg = os.environ.get("XDG_DATA_HOME")
        os.environ["HOME"] = str(self.home)
        os.environ["XDG_DATA_HOME"] = str(Path(self.tmp.name) / "xdg")
        self.old_cwd = os.getcwd()
        os.chdir(self.repo)

    def tearDown(self):
        os.chdir(self.old_cwd)
        os.environ["HOME"] = self.old_home or ""
        if self.old_db is not None:
            os.environ["LAZYPLAN_DB"] = self.old_db
        if self.old_xdg is None:
            os.environ.pop("XDG_DATA_HOME", None)
        else:
            os.environ["XDG_DATA_HOME"] = self.old_xdg
        self.tmp.cleanup()

    def run_cli(self, argv):
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            code = lpui_main(argv)
        return code, out.getvalue()

    def test_setup_lifecycle(self):
        code, _ = self.run_cli(["setup", "--yes", "--agents", "claude"])
        self.assertEqual(code, 0)
        hook = self.home / ".claude/settings.json"
        first_hook = hook.read_text()
        backups = self.home / ".lazyplan/backups"
        before = sorted(p.name for p in backups.iterdir()) if backups.is_dir() else []

        code, _ = self.run_cli(["setup", "--yes", "--agents", "claude"])
        self.assertEqual(code, 0)
        self.assertEqual(hook.read_text(), first_hook)
        after = sorted(p.name for p in backups.iterdir()) if backups.is_dir() else []
        self.assertEqual(after, before)

        code, _ = self.run_cli(["setup", "--placement", "repo", "--yes", "--agents", "claude"])
        self.assertEqual(code, 0)
        self.assertTrue((self.repo / ".agents/lazyplan/lazyplan.db").is_file())
        self.assertIn("lazyplan:start", (self.repo / "AGENTS.md").read_text())

        code, _ = self.run_cli(["doctor"])
        self.assertEqual(code, 0)

        setup.ensure(
            "ui",
            _args(),
            self.repo,
            self.home,
            "99.0",
            interactive=False,
        )
        self.assertEqual(setup.load_state(self.home).last_version, "99.0")


def _args():
    import argparse

    return argparse.Namespace(
        db="",
        version=False,
        json=True,
        yes=False,
        post_upgrade=False,
        hooks=None,
        agents_pointer=None,
        placement=None,
        agents=None,
        skills_dir=None,
        no_skills=False,
    )


if __name__ == "__main__":
    unittest.main()
