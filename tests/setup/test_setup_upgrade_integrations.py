"""Upgrade wiring: new integrations wait for an explicit install."""

import argparse
import io
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

from lazyplan.infrastructure import hook_hosts, skills
from lazyplan.presentation import setup
from lazyplan.presentation.setup import health
from tests.support.home import sandbox_home


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


class UpgradeCase(unittest.TestCase):
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

    def first_run(self, **overrides: object) -> None:
        args = make_args(**overrides)
        with redirect_stderr(io.StringIO()):
            setup.ensure("ui", args, self.repo, self.home, "1.0", interactive=False)

    def upgrade(self, version: str = "2.0", **overrides: object) -> None:
        args = make_args(**overrides)
        with redirect_stderr(io.StringIO()):
            setup.ensure("ui", args, self.repo, self.home, version, interactive=False)

    def launch_ui(self, version: str = "2.0") -> mock.MagicMock:
        """A later interactive `lpui` launch; returns the input mock."""
        args = make_args()
        with (
            mock.patch("builtins.input", return_value="1") as answer,
            redirect_stderr(io.StringIO()),
        ):
            setup.ensure("ui", args, self.repo, self.home, version, interactive=True)
        return answer

    def health_context(self, version: str = "2.0") -> health.HealthContext:
        return health.current(self.repo, self.home, version)

    def settings(self) -> Path:
        return self.home / ".claude" / "settings.json"

    def test_upgrade_leaves_a_new_hook_event_pending_without_a_tty(self):
        self.first_run()
        with mock.patch.dict(hook_hosts.EVENTS["claude"], {"future-event": "FutureEvent"}):
            self.upgrade()
            text = self.settings().read_text(encoding="utf-8")
            self.assertNotIn("future-event", text)
            state = setup.load_state(self.home)
            self.assertEqual(state.last_version, "2.0")
            self.assertNotIn("hook:claude:future-event", state.integration_choices)

    def test_lpui_leaves_the_pending_event_to_the_tui(self):
        self.first_run()
        with mock.patch.dict(hook_hosts.EVENTS["claude"], {"future-event": "FutureEvent"}):
            self.upgrade()
            answer = self.launch_ui()
            answer.assert_not_called()
            self.assertNotIn("future-event", self.settings().read_text(encoding="utf-8"))
            context = self.health_context()
            report = context.report()
            hooks = next(f for f in report.open if f.id == "hook:claude")
            self.assertIn("hook:claude:future-event", {item.id for item in hooks.items})
            context.install((hooks,))
            self.assertIn("future-event", self.settings().read_text(encoding="utf-8"))
            choices = setup.load_state(self.home).integration_choices
            self.assertEqual(choices["hook:claude:future-event"]["decision"], "installed")

    def test_new_skill_is_pending_then_installable(self):
        self.first_run()
        extra = skills.SkillSpec(name="extra", data_file="SKILL.md")
        with mock.patch.object(skills, "SKILLS", skills.SKILLS + (extra,)):
            self.upgrade()
            dest = self.home / ".claude" / "skills" / "extra" / "SKILL.md"
            self.assertFalse(dest.exists())
            self.launch_ui().assert_not_called()
            self.assertFalse(dest.exists())
            context = self.health_context()
            extra_skill = next(f for f in context.report().open if f.id == "skill:extra")
            context.install((extra_skill,))
            self.assertTrue(dest.is_file())

    def test_no_hooks_survives_later_upgrades(self):
        self.first_run(hooks=False)
        self.assertFalse(self.settings().exists())
        with mock.patch.dict(hook_hosts.EVENTS["claude"], {"future-event": "FutureEvent"}):
            self.upgrade()
            self.assertFalse(self.settings().exists())
            self.assertFalse(setup.load_state(self.home).hooks_enabled)

    def test_upgrade_keeps_the_advisory_hook_mode(self):
        self.first_run(hooks="advisory")
        self.assertIn("--mode advisory", self.settings().read_text(encoding="utf-8"))
        with mock.patch.dict(hook_hosts.TIMEOUTS, {"claude": {"*": 45}}):
            self.upgrade()
        text = self.settings().read_text(encoding="utf-8")
        self.assertIn('"timeout": 45', text)
        self.assertIn("--mode advisory", text)
        self.assertNotIn("--mode strict", text)

    def test_explicit_hooks_re_enables_install(self):
        self.first_run(hooks=False)
        setup.install_hooks(self.home, ["claude"], mode=True)
        self.assertTrue(self.settings().is_file())
        self.assertTrue(setup.load_state(self.home).hooks_enabled)


if __name__ == "__main__":
    unittest.main()
