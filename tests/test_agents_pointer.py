"""Opt-in AGENTS.md pointer for home placement."""

import io
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from lazyplan import setup  # noqa: E402
from lazyplan.cli import main as lpui_main  # noqa: E402


class PointerCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        self.home.mkdir()
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        self.old_home = os.environ.get("HOME")
        self.old_db = os.environ.pop("LAZYPLAN_DB", None)
        self.old_nosetup = os.environ.pop(setup.NO_SETUP_ENV, None)
        self.old_cwd = os.getcwd()
        os.environ["HOME"] = str(self.home)
        os.chdir(self.repo)

    def tearDown(self):
        os.chdir(self.old_cwd)
        for key, value in (
            ("HOME", self.old_home),
            ("LAZYPLAN_DB", self.old_db),
            (setup.NO_SETUP_ENV, self.old_nosetup),
        ):
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()

    def _setup(self, *extra: str) -> None:
        out = io.StringIO()
        with redirect_stdout(out):
            code = lpui_main(
                ["setup", "--yes", "--no-skills", "--no-hooks", "--placement", "home", *extra]
            )
        self.assertEqual(code, 0, out.getvalue())

    def test_default_home_placement_writes_no_agents_file(self):
        self._setup()
        self.assertFalse((self.repo / "AGENTS.md").exists())
        self.assertFalse((self.repo / ".agents").exists())

    def test_pointer_names_brief_and_the_home_database(self):
        self._setup("--agents-pointer")
        text = (self.repo / "AGENTS.md").read_text()
        self.assertIn("lpui brief", text)
        self.assertIn(str(self.home / ".lazyplan/lazyplan.db"), text)
        self.assertIn("lpui audit --since 7.days", text)
        self.assertFalse((self.repo / ".agents/lazyplan").exists())
        self.assertTrue(setup.load_state(self.home).agents_pointer)

    def test_removal_preserves_user_text(self):
        agents = self.repo / "AGENTS.md"
        agents.write_text("# Agent instructions\n\nUser rules.\n")
        self._setup("--agents-pointer")
        self.assertIn("User rules.", agents.read_text())
        self.assertIn("lpui brief", agents.read_text())
        self._setup("--no-agents-pointer")
        self.assertIn("User rules.", agents.read_text())
        self.assertNotIn("lpui brief", agents.read_text())
        self.assertFalse(setup.load_state(self.home).agents_pointer)

    def test_pointer_change_is_backed_up(self):
        agents = self.repo / "AGENTS.md"
        agents.write_text("# Agent instructions\n\nUser rules.\n")
        self._setup("--agents-pointer")
        backups = list((self.home / ".lazyplan/backups").rglob("AGENTS.md"))
        self.assertTrue(backups)
        self.assertIn("User rules.", backups[0].read_text())

    def test_state_round_trips_pointer_fields(self):
        state = setup.SetupState(agents_pointer=True, agents_file="/tmp/AGENTS.md")
        setup.save_state(state, self.home)
        loaded = setup.load_state(self.home)
        self.assertTrue(loaded.agents_pointer)
        self.assertEqual(loaded.agents_file, "/tmp/AGENTS.md")


if __name__ == "__main__":
    unittest.main()
