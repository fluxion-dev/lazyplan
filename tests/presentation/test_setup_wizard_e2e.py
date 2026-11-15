"""End to end: a due wizard opens the real screen and applies real setup.

The pilot starts the app with the startup trigger, never replacing the screen
factory, jumps to Review through the rail, applies the remembered defaults, and
checks the files and setup state the apply path leaves behind.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from collections.abc import Iterable
from pathlib import Path
from typing import Any
from unittest import mock

from lazyplan.infrastructure.host_models import HostCatalog
from lazyplan.infrastructure.skills import AgentHost
from lazyplan.presentation import setup
from tests.support.home import sandbox_home

try:
    from textual.widgets import Button, OptionList

    from lazyplan.presentation.tui import create_app
    from lazyplan.presentation.tui.controllers.setup import current
    from lazyplan.presentation.tui.launch import Restart
    from lazyplan.presentation.tui.screens import SetupWizardScreen
except ImportError:  # pragma: no cover - textual not installed
    create_app = None  # type: ignore[assignment]
    current = None  # type: ignore[assignment]
    Restart = None  # type: ignore[assignment]
    SetupWizardScreen = None  # type: ignore[assignment]
    Button = OptionList = None  # type: ignore[assignment,misc]


def _catalogs(
    hosts: Iterable[str],
    _home: Path,
    _root: Path | None,
) -> dict[str, HostCatalog]:
    """Offline catalogs: no host binary is ever executed."""
    return {
        host: HostCatalog(
            host=host,
            label=host.title(),
            models=("tiny", "large"),
            tier_defaults={"fast": "tiny", "standard": "tiny", "deep": "large"},
        )
        for host in hosts
    }


def _detected(_home: Path | None = None) -> list[AgentHost]:
    """One detected host, so the defaults write skills, profiles, and hooks."""
    return [AgentHost("claude", "Claude Code", True, "test fixture")]


@unittest.skipUnless(create_app is not None, "textual not installed")
class SetupWizardEndToEndTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        base = Path(self.tmp.name)
        self.home = base / "home"
        self.home.mkdir()
        self.repo = base / "repo"
        self.repo.mkdir()
        (self.repo / ".git").mkdir()
        self.db = str(base / "plans.db")
        self.old_db = os.environ.pop("LAZYPLAN_DB", None)
        sandbox_home(self, self.home)
        for target, replacement in (
            ("lazyplan.infrastructure.host_models.discover_all", _catalogs),
            ("lazyplan.infrastructure.skills.detect_agents", _detected),
        ):
            patcher = mock.patch(target, side_effect=replacement)
            patcher.start()
            self.addCleanup(patcher.stop)

    def tearDown(self) -> None:
        if self.old_db is not None:
            os.environ["LAZYPLAN_DB"] = self.old_db
        self.tmp.cleanup()

    def launch(self) -> Any:
        return create_app(self.db, wizard_check=current(self.repo, self.home, "1.0"))

    def state(self, **fields: Any) -> None:
        setup.save_state(setup.SetupState(placement="home", agents=[], **fields), self.home)

    async def settle(self, pilot: Any) -> None:
        for _ in range(3):
            await pilot.app.workers.wait_for_complete()
            await pilot.pause()

    async def jump_to_review(self, pilot: Any, screen: Any) -> None:
        """Pick Review on the rail, the same gesture a user makes."""
        rail = screen.query_one("#setup-rail-list", OptionList)
        keys = [step.key for step in screen._steps]
        rail.highlighted = keys.index("review")
        rail.action_select()
        await self.settle(pilot)

    async def test_a_fresh_install_applies_the_defaults_through_the_real_screen(
        self,
    ) -> None:
        app = self.launch()
        async with app.run_test(size=(120, 40)) as pilot:
            await self.settle(pilot)
            screen = app.screen
            self.assertIsInstance(screen, SetupWizardScreen)
            self.assertTrue(app.setup_controller.pending)
            self.assertEqual(screen.step.key, "welcome")
            self.assertEqual(screen.session.draft.agents, ["claude"])

            await self.jump_to_review(pilot, screen)
            self.assertEqual(screen.step.key, "review")
            screen.query_one("#setup-next", Button).press()
            await self.settle(pilot)
            self.assertIn("Setup applied", str(screen.query_one("#setup-apply-status").render()))
            screen.query_one("#setup-next", Button).press()
            await self.settle(pilot)

        self.assertTrue((self.home / ".lazyplan" / "setup.json").is_file())
        self.assertTrue((self.home / ".lazyplan" / "lazyplan.db").is_file())
        self.assertTrue((self.home / ".lazyplan" / "agents.json").is_file())
        self.assertTrue((self.home / ".claude" / "skills" / "lazyplan" / "SKILL.md").is_file())
        self.assertTrue((self.home / ".claude" / "agents" / "lazyplan-scout.md").is_file())
        self.assertTrue((self.home / ".claude" / "settings.json").is_file())
        state = setup.load_state(self.home)
        self.assertEqual(state.wizard_pending, "")
        self.assertEqual(state.wizard_completed, "1.0")
        self.assertEqual(state.agents, ["claude"])
        self.assertEqual(app.return_value, Restart(("claude",)))

    async def test_finishing_later_from_the_real_screen_keeps_the_pending_marker(
        self,
    ) -> None:
        self.state(last_version="1.0", wizard_pending="version")
        before = (self.home / ".lazyplan" / "setup.json").read_text(encoding="utf-8")
        app = self.launch()
        async with app.run_test(size=(120, 40)) as pilot:
            await self.settle(pilot)
            self.assertIsInstance(app.screen, SetupWizardScreen)
            await pilot.press("l")
            await self.settle(pilot)
            self.assertEqual(len(app.screen_stack), 1)
            self.assertTrue(app.setup_controller.pending)
        after = (self.home / ".lazyplan" / "setup.json").read_text(encoding="utf-8")
        self.assertEqual(after, before)
        self.assertEqual(setup.load_state(self.home).wizard_pending, "version")
        self.assertFalse((self.home / ".claude").exists())

    async def test_the_key_reopens_the_real_screen_on_demand(self) -> None:
        self.state(last_version="1.0", wizard_completed="1.0")
        with (
            mock.patch("lazyplan.presentation.setup.triggers._pending_items", return_value=()),
            mock.patch("lazyplan.presentation.setup.triggers._profile_drift", return_value=False),
        ):
            app = self.launch()
            async with app.run_test(size=(120, 40)) as pilot:
                await self.settle(pilot)
                self.assertEqual(len(app.screen_stack), 1)
                await pilot.press("S")
                await self.settle(pilot)
                self.assertIsInstance(app.screen, SetupWizardScreen)
                self.assertTrue(app.screen.session is not None)
                self.assertEqual(app.screen.session.draft.agents, ["claude"])
