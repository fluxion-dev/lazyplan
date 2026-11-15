"""Pilot matrix: every step at both sizes, and a prefilled resume."""

from __future__ import annotations

import tempfile
import unittest
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from lazyplan.infrastructure.host_models import HostCatalog
from lazyplan.presentation import setup
from tests.support.home import sandbox_home

try:
    from textual.widgets import Button, Checkbox, Input, Label, OptionList, Select, Static

    from lazyplan.presentation.tui import create_app
    from lazyplan.presentation.tui.screens import SetupWizardScreen, WizardResult
except ImportError:  # pragma: no cover - textual not installed
    create_app = None  # type: ignore[assignment]
    SetupWizardScreen = WizardResult = None  # type: ignore[assignment]
    Button = Checkbox = Input = Label = OptionList = Select = Static = None  # type: ignore[assignment,misc]


def _catalogs(hosts: Iterable[str], _home: Path, _root: Path | None) -> dict[str, HostCatalog]:
    return {
        host: HostCatalog(
            host=host,
            label=host.title(),
            models=("tiny", "large"),
            tier_defaults={"fast": "tiny", "standard": "tiny", "deep": "large"},
        )
        for host in hosts
    }


STEP_CONTROLS: dict[str, str] = {
    "welcome": "#setup-welcome",
    "placement": "#setup-placement-list",
    "agents": "#setup-agent-opencode",
    "hooks": "#setup-hooks-mode",
    "models": "#setup-tier-opencode-fast",
    "roles": "#setup-role-tier-scout",
    "integrations": "#setup-integration-skill-lazyplan",
    "appearance": "#setup-theme",
    "review": "#setup-apply-status",
}


@unittest.skipUnless(create_app is not None, "textual not installed")
class SetupWizardPilotTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        base = Path(self.tmp.name)
        self.home = base / "home"
        self.home.mkdir()
        self.repo = base / "repo"
        self.repo.mkdir()
        (self.repo / ".git").mkdir()
        self.db = str(base / "wizard.db")
        sandbox_home(self, self.home)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def session(self, state: setup.SetupState | None = None) -> setup.SetupSession:
        session = setup.SetupSession.load(
            self.repo, self.home, "1.0", state=state, discover=_catalogs
        )
        session.set_agents(["opencode"])
        return session

    async def offer(self, app: Any, pilot: Any, session: setup.SetupSession) -> Any:
        screen = SetupWizardScreen(session, checks=lambda: ())
        app.push_screen(screen, lambda _result: None)
        await pilot.pause()
        return screen

    async def test_every_step_renders_at_compact_and_wide(self) -> None:
        for size, style in (((72, 24), "compact"), ((140, 40), "wide")):
            session = self.session()
            app = create_app(self.db)
            async with app.run_test(size=size) as pilot:
                screen = await self.offer(app, pilot, session)
                self.assertTrue(screen.has_class(style))
                self.assertEqual(screen.query_one("#setup-rail").display, style == "wide")
                for index, step in enumerate(screen._steps):
                    await screen._select(index)
                    await pilot.pause()
                    self.assertEqual(screen.step.key, step.key)
                    title = str(screen.query_one("#setup-step-title", Label).render())
                    self.assertIn(step.title, title)
                    copy = str(screen.query_one("#setup-copy", Static).render())
                    self.assertTrue(copy.strip())
                    self.assertTrue(screen.query_one(STEP_CONTROLS[step.key]) is not None)
                    self.assertFalse(screen.query_one("#setup-errors", Static).display)

    async def test_finish_later_writes_nothing_at_compact(self) -> None:
        session = self.session()
        app = create_app(self.db)
        async with app.run_test(size=(72, 24)) as pilot:
            await self.offer(app, pilot, session)
            await pilot.press("l")
            await pilot.pause()
            self.assertNotIsInstance(app.screen, SetupWizardScreen)
            self.assertFalse((self.home / ".lazyplan" / "setup.json").exists())

    async def test_cancel_after_edits_at_compact_asks_first(self) -> None:
        session = self.session()
        app = create_app(self.db)
        async with app.run_test(size=(72, 24)) as pilot:
            screen = await self.offer(app, pilot, session)
            screen.session.set_hooks_mode("advisory")
            await pilot.press("escape")
            await pilot.pause()
            from lazyplan.presentation.tui.screens.forms import ConfirmScreen

            self.assertIsInstance(app.screen, ConfirmScreen)

    async def test_help_names_how_to_reopen_the_wizard(self) -> None:
        from lazyplan.presentation.tui.screens import HelpScreen

        app = create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            app.push_screen(HelpScreen())
            await pilot.pause()
            body = str(app.screen.query_one("#help-scroll Static", Static).render())
            self.assertIn("reopen the setup wizard", body)
            self.assertIn("finish later", body)

    async def test_resume_prefills_the_remembered_choices(self) -> None:
        state = setup.SetupState(
            placement="home",
            agents=["opencode"],
            hooks_mode="advisory",
            agents_pointer=True,
            theme="lazyplan-void",
        )
        session = self.session(state)
        app = create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            screen = await self.offer(app, pilot, session)
            await screen._select([s.key for s in screen._steps].index("agents"))
            await pilot.pause()
            self.assertTrue(screen.query_one("#setup-agent-opencode", Checkbox).value)
            await screen._select([s.key for s in screen._steps].index("hooks"))
            await pilot.pause()
            self.assertEqual(screen.query_one("#setup-hooks-mode", Select).value, "advisory")
            self.assertTrue(screen.query_one("#setup-pointer", Checkbox).value)
            await screen._select([s.key for s in screen._steps].index("appearance"))
            await pilot.pause()
            self.assertEqual(screen.query_one("#setup-theme", Select).value, "lazyplan-void")


if __name__ == "__main__":
    unittest.main()
