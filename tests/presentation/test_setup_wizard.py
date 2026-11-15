"""The setup wizard shell: steps, navigation, and leaving without writes."""

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
    from textual.widgets import Button, Label, OptionList

    from lazyplan.presentation.tui import create_app
    from lazyplan.presentation.tui.screens import SetupWizardScreen, WizardResult
    from lazyplan.presentation.tui.screens.forms import ConfirmScreen
except ImportError:  # pragma: no cover - textual not installed
    create_app = None  # type: ignore[assignment]
    SetupWizardScreen = WizardResult = None  # type: ignore[assignment]
    ConfirmScreen = None  # type: ignore[assignment]
    Button = Label = OptionList = None  # type: ignore[assignment,misc]


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


@unittest.skipUnless(create_app is not None, "textual not installed")
class SetupWizardShellTest(unittest.IsolatedAsyncioTestCase):
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

    def session(self) -> setup.SetupSession:
        return setup.SetupSession.load(self.repo, self.home, "1.0", discover=_catalogs)

    async def offer(
        self,
        app: Any,
        pilot: Any,
        session: setup.SetupSession,
        start: str = "",
    ) -> tuple[Any, list[WizardResult]]:
        results: list[WizardResult] = []
        screen = SetupWizardScreen(session, start=start)
        app.push_screen(screen, results.append)
        await pilot.pause()
        return screen, results

    def counter(self, app: Any) -> str:
        return str(app.screen.query_one("#setup-counter", Label).render())

    async def test_the_rail_lists_every_visible_step(self) -> None:
        session = self.session()
        app = create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            screen, _results = await self.offer(app, pilot, session)
            rail = screen.query_one("#setup-rail-list", OptionList)
            self.assertEqual(rail.option_count, len(session.steps()))
            self.assertIn("Step 1 of", self.counter(app))

    async def test_next_moves_forward_and_back_returns(self) -> None:
        session = self.session()
        app = create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            screen, _results = await self.offer(app, pilot, session)
            await pilot.press("n")
            await pilot.pause()
            self.assertEqual(screen._index, 1)
            self.assertIn("Step 2 of", self.counter(app))
            await pilot.press("b")
            await pilot.pause()
            self.assertEqual(screen._index, 0)

    async def test_the_last_primary_button_is_apply(self) -> None:
        session = self.session()
        app = create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            screen, _results = await self.offer(app, pilot, session, start="review")
            button = screen.query_one("#setup-next", Button)
            self.assertEqual(str(button.label), "Apply")
            self.assertFalse(button.disabled)

    async def test_finish_later_dismisses_and_writes_nothing(self) -> None:
        session = self.session()
        app = create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            _screen, results = await self.offer(app, pilot, session)
            await pilot.press("l")
            await pilot.pause()
            self.assertNotIsInstance(app.screen, SetupWizardScreen)
        self.assertIsInstance(results[-1], WizardResult)
        self.assertFalse(results[-1].applied)
        self.assertFalse((self.home / ".lazyplan" / "setup.json").exists())
        self.assertFalse((self.home / ".lazyplan" / "agents.json").exists())
        self.assertFalse((self.home / ".agents").exists())

    async def test_escape_without_edits_closes_immediately(self) -> None:
        session = self.session()
        app = create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            _screen, results = await self.offer(app, pilot, session)
            await pilot.press("escape")
            await pilot.pause()
            self.assertNotIsInstance(app.screen, SetupWizardScreen)
        self.assertFalse(results[-1].applied)

    async def test_escape_with_edits_asks_before_discarding(self) -> None:
        session = self.session()
        app = create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            screen, results = await self.offer(app, pilot, session)
            screen.session.set_hooks_mode("advisory")
            await pilot.press("escape")
            await pilot.pause()
            self.assertIsInstance(app.screen, ConfirmScreen)
            await pilot.click("#ok")
            await pilot.pause()
            self.assertNotIsInstance(app.screen, SetupWizardScreen)
        self.assertFalse(results[-1].applied)

    async def test_discarding_can_be_cancelled(self) -> None:
        session = self.session()
        app = create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            screen, results = await self.offer(app, pilot, session)
            screen.session.set_hooks_mode("advisory")
            await pilot.press("escape")
            await pilot.pause()
            await pilot.click("#cancel")
            await pilot.pause()
            self.assertIsInstance(app.screen, SetupWizardScreen)
        self.assertEqual(results, [])
        self.assertEqual(screen.session.draft.hooks_mode, "advisory")

    async def test_edits_survive_back_and_next(self) -> None:
        session = self.session()
        app = create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            screen, _results = await self.offer(app, pilot, session)
            screen.session.set_hooks_mode("advisory")
            await pilot.press("n")
            await pilot.press("n")
            await pilot.press("b")
            await pilot.press("b")
            await pilot.pause()
            self.assertEqual(screen._index, 0)
            self.assertEqual(session.draft.hooks_mode, "advisory")

    async def test_the_rail_jumps_to_a_step(self) -> None:
        session = self.session()
        app = create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            screen, _results = await self.offer(app, pilot, session)
            rail = screen.query_one("#setup-rail-list", OptionList)
            rail.highlighted = 2
            rail.action_select()
            await pilot.pause()
            self.assertEqual(screen._index, 2)
            self.assertIn("Step 3 of", self.counter(app))

    async def test_unknown_start_step_opens_the_first_step(self) -> None:
        session = self.session()
        app = create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            screen, _results = await self.offer(app, pilot, session, start="nope")
            self.assertEqual(screen._index, 0)

    async def test_compact_hides_the_rail_and_wide_shows_it(self) -> None:
        session = self.session()
        app = create_app(self.db)
        async with app.run_test(size=(72, 24)) as pilot:
            screen, _results = await self.offer(app, pilot, session)
            self.assertTrue(screen.has_class("compact"))
            self.assertFalse(screen.query_one("#setup-rail").display)
        app = create_app(self.db)
        async with app.run_test(size=(140, 40)) as pilot:
            screen, _results = await self.offer(app, pilot, session)
            self.assertTrue(screen.has_class("wide"))
            self.assertTrue(screen.query_one("#setup-rail").display)

    async def test_the_explanation_names_the_step_and_what_it_changes(self) -> None:
        session = self.session()
        app = create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            screen, _results = await self.offer(app, pilot, session)
            copy = str(screen.query_one("#setup-copy").render())
            self.assertIn("Nothing is written", copy)
            title = str(screen.query_one("#setup-step-title", Label).render())
            self.assertEqual(title, "Welcome")


if __name__ == "__main__":
    unittest.main()
