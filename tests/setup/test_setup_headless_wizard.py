"""Headless, agent, and doctor paths never open or block on the wizard."""

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
from lazyplan.presentation.cli.parser import package_version
from lazyplan.presentation.setup import triggers
from tests.support.home import sandbox_home

WIZARD = "lazyplan.presentation.setup.apply.run_wizard"
APPLY = "lazyplan.presentation.setup.apply.apply_choice"


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


class HeadlessWizardCase(unittest.TestCase):
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

    def ensure(self, cmd: str, **kwargs: object) -> None:
        interactive = bool(kwargs.pop("interactive", True))
        version = str(kwargs.pop("version", "1.0"))
        with redirect_stderr(io.StringIO()):
            setup.ensure(cmd, make_args(**kwargs), self.repo, self.home, version, interactive)

    def test_skip_commands_never_touch_setup_or_the_wizard(self) -> None:
        for cmd in setup.SKIP_COMMANDS:
            with self.subTest(cmd=cmd), mock.patch(APPLY) as apply, mock.patch(WIZARD) as wizard:
                self.ensure(cmd)
            apply.assert_not_called()
            wizard.assert_not_called()
        self.assertFalse((self.home / ".lazyplan/setup.json").exists())

    def test_agent_writes_set_up_silently_without_a_wizard(self) -> None:
        for cmd in ("list", "show", "add", "update", "feed", "note", "claim", "export", "mcp"):
            with self.subTest(cmd=cmd):
                self.clean_home()
                with mock.patch(WIZARD) as wizard:
                    self.ensure(cmd)
                wizard.assert_not_called()
                state = setup.load_state(self.home)
                self.assertEqual(state.wizard_pending, "")
                self.assertEqual(state.last_version, "1.0")
                self.assertTrue((self.home / ".claude/settings.json").is_file())

    def test_hooks_and_mcp_never_defer(self) -> None:
        for cmd in ("hook", "mcp", "completion"):
            with self.subTest(cmd=cmd):
                with mock.patch.object(triggers, "textual_available", return_value=True):
                    self.assertFalse(triggers.tui_owns_setup(cmd, make_args(), True))

    def test_json_and_yes_never_prompt_the_wizard(self) -> None:
        for overrides in ({"json": True}, {"yes": True}):
            with self.subTest(**overrides):
                self.clean_home()
                with mock.patch(WIZARD) as wizard:
                    self.ensure("ui", **overrides)
                wizard.assert_not_called()
                self.assertEqual(setup.load_state(self.home).wizard_pending, "")

    def test_a_non_terminal_ui_run_never_prompts(self) -> None:
        with mock.patch(WIZARD) as wizard:
            self.ensure("ui", interactive=False)
        wizard.assert_not_called()
        self.assertEqual(setup.load_state(self.home).wizard_pending, "")

    def test_no_setup_environment_skips_the_wizard_and_the_writes(self) -> None:
        with (
            mock.patch.dict(os.environ, {setup.NO_SETUP_ENV: "1"}),
            mock.patch(APPLY) as apply,
            mock.patch(WIZARD) as wizard,
        ):
            self.ensure("ui")
        apply.assert_not_called()
        wizard.assert_not_called()
        self.assertFalse((self.home / ".lazyplan").exists())

    def test_an_explicit_database_turns_the_wizard_off(self) -> None:
        with mock.patch(WIZARD) as wizard:
            self.ensure("ui", db=str(Path(self.tmp.name) / "owned.db"))
        wizard.assert_not_called()
        self.assertEqual(setup.load_state(self.home).wizard_pending, "")
        self.assertFalse((self.home / ".lazyplan/setup.json").exists())

    def test_a_pending_wizard_still_opens_the_database(self) -> None:
        self.ensure("ui")
        self.assertEqual(setup.load_state(self.home).wizard_pending, triggers.FRESH)
        out = io.StringIO()
        with redirect_stdout(out):
            code = lpui_main(["list"])
        self.assertEqual(code, 0)
        self.assertIn("No active plans", out.getvalue())

    def test_doctor_reports_one_pending_wizard_line(self) -> None:
        self.ensure("ui")
        out = io.StringIO()
        with (
            mock.patch.object(triggers, "_pending_items", return_value=()),
            mock.patch.object(triggers, "_profile_drift", return_value=False),
            redirect_stdout(out),
        ):
            lpui_main(["doctor"])
        lines = [line for line in out.getvalue().splitlines() if line.startswith("wizard:")]
        self.assertEqual(len(lines), 1, out.getvalue())
        self.assertIn(triggers.FRESH, lines[0])
        self.assertIn("finish setting lazyplan up", lines[0])

    def test_doctor_carries_the_wizard_reason_in_json(self) -> None:
        self.ensure("ui")
        out = io.StringIO()
        with (
            mock.patch.object(triggers, "_pending_items", return_value=()),
            mock.patch.object(triggers, "_profile_drift", return_value=False),
            redirect_stdout(out),
        ):
            lpui_main(["doctor", "--json"])
        report = json.loads(out.getvalue())
        self.assertTrue(report["wizard"]["due"])
        self.assertEqual(report["wizard"]["reason"], triggers.FRESH)

    def test_doctor_never_opens_the_wizard(self) -> None:
        with (
            mock.patch("lazyplan.presentation.tui.run") as run,
            mock.patch(WIZARD) as wizard,
        ):
            self.ensure("ui")
            out = io.StringIO()
            with redirect_stdout(out):
                lpui_main(["doctor"])
        run.assert_not_called()
        wizard.assert_not_called()

    def test_doctor_is_quiet_when_nothing_is_due(self) -> None:
        self.ensure("ui", version=package_version())
        triggers.clear_pending(setup.load_state(self.home), package_version(), self.home)
        out = io.StringIO()
        with (
            mock.patch.object(triggers, "_pending_items", return_value=()),
            mock.patch.object(triggers, "_profile_drift", return_value=False),
            redirect_stdout(out),
        ):
            lpui_main(["doctor"])
        self.assertNotIn("wizard:", out.getvalue())

    def clean_home(self) -> None:
        """Drop setup state and written resources between matrix rows."""
        for path in (self.home / ".lazyplan", self.home / ".claude"):
            if not path.exists():
                continue
            for child in sorted(path.rglob("*"), reverse=True):
                child.unlink() if child.is_file() else child.rmdir()
            path.rmdir()


if __name__ == "__main__":
    unittest.main()
