"""The startup and fallback matrix: every trigger and every silent path.

The terminal-wizard pseudo-terminal suite (`test_setup_pty.py`) stays the
end-to-end proof for `lpui setup`; this file pins the split around it.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from lazyplan.presentation import setup
from lazyplan.presentation.cli import main as lpui_main
from lazyplan.presentation.cli.commands import setup as setup_command
from lazyplan.presentation.cli.parser import package_version
from lazyplan.presentation.setup import triggers
from tests.support.home import sandbox_home

WIZARD = "lazyplan.presentation.setup.run_wizard"
UI_WIZARD = "lazyplan.presentation.setup.apply.run_wizard"


class Tty(io.StringIO):
    """A stream that claims to be a terminal."""

    def isatty(self) -> bool:
        return True


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
        "agents": "claude",
        "skills_dir": None,
        "no_skills": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


class WizardSplitCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        self.home.mkdir()
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q", self.repo], check=True)
        self.old_db = os.environ.pop("LAZYPLAN_DB", None)
        self.old_setup = os.environ.pop(setup.NO_SETUP_ENV, None)
        self.old_cwd = os.getcwd()
        sandbox_home(self, self.home)
        os.chdir(self.repo)

    def tearDown(self) -> None:
        os.chdir(self.old_cwd)
        for key, value in (
            ("LAZYPLAN_DB", self.old_db),
            (setup.NO_SETUP_ENV, self.old_setup),
        ):
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()

    def ensure(self, cmd: str, version: str = "1.0", **kwargs: object) -> None:
        interactive = bool(kwargs.pop("interactive", True))
        with redirect_stderr(io.StringIO()):
            setup.ensure(cmd, make_args(**kwargs), self.repo, self.home, version, interactive)

    def test_only_the_screen_defers_among_the_human_commands(self) -> None:
        with mock.patch.object(triggers, "textual_available", return_value=True):
            for cmd in setup.HUMAN_COMMANDS:
                with self.subTest(cmd=cmd):
                    self.assertEqual(triggers.tui_owns_setup(cmd, make_args(), True), cmd == "ui")

    def test_the_terminal_wizard_stays_for_an_explicit_setup(self) -> None:
        with (
            mock.patch.object(setup.setup_ui, "stdin_tty", return_value=True),
            mock.patch(WIZARD, return_value=None) as wizard,
            redirect_stderr(Tty()),
        ):
            setup_command._cmd_setup(None, make_args(), "human")
        wizard.assert_called_once()

    def test_the_terminal_wizard_stays_without_textual(self) -> None:
        with (
            mock.patch.object(triggers, "textual_available", return_value=False),
            mock.patch(UI_WIZARD, return_value=None) as wizard,
            redirect_stderr(io.StringIO()),
        ):
            setup.ensure("ui", make_args(), self.repo, self.home, "1.0", True)
        wizard.assert_called_once()

    def test_json_stdout_stays_clean_on_a_first_run(self) -> None:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = lpui_main(["list", "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out.getvalue()), [])
        self.assertEqual(err.getvalue(), "")

    def test_the_cli_records_fresh_before_version(self) -> None:
        self.ensure("ui")
        self.assertEqual(setup.load_state(self.home).wizard_pending, triggers.FRESH)
        triggers.clear_pending(setup.load_state(self.home), "1.0", self.home)
        self.ensure("ui", version="2.0")
        state = setup.load_state(self.home)
        self.assertEqual(state.wizard_pending, triggers.VERSION)
        self.assertEqual(state.wizard_version, "2.0")

    def test_a_completed_wizard_clears_the_reason(self) -> None:
        from lazyplan.presentation.setup.session import SetupSession

        self.ensure("ui", version=package_version())
        self.assertTrue(setup.load_state(self.home).wizard_pending)
        with mock.patch("lazyplan.infrastructure.host_models.discover_all", return_value={}):
            session = SetupSession.load(self.repo, self.home, package_version())
        session.draft.theme = "lazyplan-light"
        with redirect_stderr(io.StringIO()):
            session.apply()
        state = setup.load_state(self.home)
        self.assertEqual(state.wizard_pending, "")
        self.assertEqual(state.wizard_completed, package_version())
        self.assertEqual(state.theme, "lazyplan-light")
        with (
            mock.patch.object(triggers, "_pending_items", return_value=()),
            mock.patch.object(triggers, "_profile_drift", return_value=False),
        ):
            self.assertFalse(triggers.detect(self.repo, self.home, package_version(), state).due)

    def test_every_agent_and_skip_command_leaves_the_state_alone(self) -> None:
        setup.save_state(
            setup.SetupState(
                placement="home",
                agents=["claude"],
                last_version="1.0",
                wizard_completed="1.0",
            ),
            self.home,
        )
        path = setup.state_path(self.home)
        before = path.read_text(encoding="utf-8")
        for cmd in (*setup.SKIP_COMMANDS, "list", "dispatch", "note", "hook", "mcp"):
            with self.subTest(cmd=cmd):
                self.ensure(cmd)
                self.assertEqual(path.read_text(encoding="utf-8"), before)
        self.assertEqual(setup.load_state(self.home).wizard_pending, "")


if __name__ == "__main__":
    unittest.main()
