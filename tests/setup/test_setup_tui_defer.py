"""An interactive `lpui` leaves the wizard to the screen, never the terminal."""

import argparse
import io
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

from lazyplan.presentation import setup
from lazyplan.presentation.setup import triggers
from tests.support.home import sandbox_home

WIZARD = "lazyplan.presentation.setup.apply.run_wizard"


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


class TuiDeferCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        self.home.mkdir()
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q", self.repo], check=True)
        self.old_db = os.environ.pop("LAZYPLAN_DB", None)
        sandbox_home(self, str(self.home))

    def tearDown(self) -> None:
        if self.old_db is not None:
            os.environ["LAZYPLAN_DB"] = self.old_db
        self.tmp.cleanup()

    def ensure(self, cmd: str = "ui", **kwargs: object) -> tuple[int, str]:
        interactive = kwargs.pop("interactive", True)
        version = str(kwargs.pop("version", "1.0"))
        err = io.StringIO()
        with redirect_stderr(err):
            setup.ensure(
                cmd,
                make_args(**kwargs),
                self.repo,
                self.home,
                version,
                interactive=interactive,
            )
        return 0, err.getvalue()

    def test_interactive_ui_marks_fresh_and_skips_the_terminal_wizard(self) -> None:
        with mock.patch(WIZARD) as wizard:
            _code, err = self.ensure()
        wizard.assert_not_called()
        state = setup.load_state(self.home)
        self.assertEqual(state.wizard_pending, triggers.FRESH)
        self.assertEqual(state.wizard_version, "1.0")
        self.assertEqual(state.last_version, "1.0")
        self.assertTrue((self.home / ".lazyplan/lazyplan.db").is_file())
        self.assertTrue((self.home / ".claude/settings.json").is_file())
        self.assertNotIn("Setup complete", err)

    def test_version_change_defers_with_the_version_reason(self) -> None:
        self.ensure(interactive=False, version="0.9")
        triggers.clear_pending(setup.load_state(self.home), "0.9", self.home)
        with mock.patch(WIZARD) as wizard:
            self.ensure()
        wizard.assert_not_called()
        state = setup.load_state(self.home)
        self.assertEqual(state.wizard_pending, triggers.VERSION)
        self.assertEqual(state.wizard_version, "1.0")
        self.assertEqual(state.last_version, "1.0")

    def test_a_remembered_marker_survives_a_quiet_launch(self) -> None:
        self.ensure()
        with mock.patch(WIZARD) as wizard:
            self.ensure()
        wizard.assert_not_called()
        self.assertEqual(setup.load_state(self.home).wizard_pending, triggers.FRESH)

    def test_a_non_terminal_ui_run_keeps_the_silent_path(self) -> None:
        with mock.patch(WIZARD) as wizard:
            self.ensure(interactive=False)
        wizard.assert_not_called()
        self.assertEqual(setup.load_state(self.home).wizard_pending, "")

    def test_json_and_yes_never_defer_or_prompt(self) -> None:
        for overrides in ({"json": True}, {"yes": True}):
            with self.subTest(**overrides):
                case = Path(self.tmp.name) / f"case-{'-'.join(overrides)}"
                home = case / "home"
                home.mkdir(parents=True)
                sandbox_home(self, str(home))
                with mock.patch(WIZARD) as wizard:
                    with redirect_stderr(io.StringIO()):
                        setup.ensure(
                            "ui",
                            make_args(**overrides),
                            self.repo,
                            home,
                            "1.0",
                            interactive=True,
                        )
                wizard.assert_not_called()
                self.assertEqual(setup.load_state(home).wizard_pending, "")

    def test_agent_commands_never_defer(self) -> None:
        with mock.patch(WIZARD) as wizard:
            self.ensure(cmd="list")
        wizard.assert_not_called()
        self.assertEqual(setup.load_state(self.home).wizard_pending, "")

    def test_without_textual_the_terminal_wizard_still_runs(self) -> None:
        with (
            mock.patch.object(triggers, "textual_available", return_value=False),
            mock.patch(WIZARD, return_value=None) as wizard,
        ):
            result = setup.ensure("ui", make_args(), self.repo, self.home, "1.0", interactive=True)
        wizard.assert_called_once()
        self.assertIsNone(result)
        self.assertEqual(setup.load_state(self.home).wizard_pending, "")

    def test_no_setup_environment_skips_everything(self) -> None:
        with (
            mock.patch.dict(os.environ, {setup.NO_SETUP_ENV: "1"}),
            mock.patch(WIZARD) as wizard,
            mock.patch.object(setup, "apply_choice") as apply,
        ):
            self.ensure()
        wizard.assert_not_called()
        apply.assert_not_called()
        self.assertFalse((self.home / ".lazyplan/setup.json").exists())

    def test_tui_owns_setup_follows_the_command_and_the_flags(self) -> None:
        args = make_args()
        with mock.patch.object(triggers, "textual_available", return_value=True):
            self.assertTrue(triggers.tui_owns_setup("ui", args, True))
            self.assertFalse(triggers.tui_owns_setup("ui", make_args(json=True), True))
            self.assertFalse(triggers.tui_owns_setup("ui", make_args(yes=True), True))
            self.assertFalse(triggers.tui_owns_setup("ui", args, False))
            self.assertFalse(triggers.tui_owns_setup("list", args, True))
        with mock.patch.object(triggers, "textual_available", return_value=False):
            self.assertFalse(triggers.tui_owns_setup("ui", args, True))


if __name__ == "__main__":
    unittest.main()
