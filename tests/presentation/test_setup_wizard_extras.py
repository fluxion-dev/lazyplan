"""Integrations, appearance preview, and read-only checks."""

from __future__ import annotations

import tempfile
import unittest
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from lazyplan.infrastructure.host_models import HostCatalog
from lazyplan.presentation import setup
from lazyplan.presentation.setup.health import GH_AUTH, LPUI, HealthFinding
from tests.support.home import sandbox_home

try:
    from textual.widgets import Input, Select, Static

    from lazyplan.presentation.tui import create_app
    from lazyplan.presentation.tui.screens import SetupWizardScreen
    from lazyplan.presentation.tui.theme.themes import THEME_NAMES
    from lazyplan.presentation.tui.widgets.setup_controls import widget_id
except ImportError:  # pragma: no cover - textual not installed
    create_app = None  # type: ignore[assignment]
    SetupWizardScreen = None  # type: ignore[assignment]

    def widget_id(text: str) -> str:  # pragma: no cover - textual not installed
        return text

    Input = Select = Static = None  # type: ignore[assignment,misc]
    THEME_NAMES = ("lazyplan-dark", "lazyplan-void", "lazyplan-light")


def _catalogs(hosts: Iterable[str], _home: Path, _root: Path | None) -> dict[str, HostCatalog]:
    return {host: HostCatalog(host=host, label=host.title()) for host in hosts}


def _checks(findings: tuple[HealthFinding, ...]) -> Any:
    return lambda: findings


@unittest.skipUnless(create_app is not None, "textual not installed")
class SetupWizardExtrasTest(unittest.IsolatedAsyncioTestCase):
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
        session = setup.SetupSession.load(self.repo, self.home, "1.0", discover=_catalogs)
        session.set_agents(["opencode"])
        return session

    async def offer(
        self,
        app: Any,
        pilot: Any,
        session: setup.SetupSession,
        start: str,
        checks: Any = None,
    ) -> Any:
        screen = SetupWizardScreen(
            session, start=start, checks=checks if checks is not None else _checks(())
        )
        app.push_screen(screen, lambda _result: None)
        await pilot.pause()
        return screen

    async def settle(self, pilot: Any) -> None:
        await pilot.pause()
        await pilot.app.workers.wait_for_complete()
        await pilot.pause()

    async def test_each_pending_item_offers_install_defer_and_never(self) -> None:
        session = self.session()
        app = create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            screen = await self.offer(app, pilot, session, "integrations")
            selects = list(screen.query("#setup-panel Select"))
            self.assertEqual(len(selects), len(session.pending))
            for select in selects:
                values = [value for _label, value in select._options]
                self.assertEqual(values, ["install", "defer", "never"])

    async def test_defer_and_never_are_stored_per_item(self) -> None:
        session = self.session()
        first, second = session.pending[0], session.pending[1]
        app = create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            screen = await self.offer(app, pilot, session, "integrations")
            screen.query_one(f"#setup-integration-{widget_id(first.id)}", Select).value = "defer"
            await pilot.pause()
            screen.query_one(f"#setup-integration-{widget_id(second.id)}", Select).value = "never"
            await pilot.pause()
            self.assertEqual(session.draft.integrations[first.id], "defer")
            self.assertEqual(session.draft.integrations[second.id], "never")

    async def test_the_theme_preview_updates_the_app_and_the_draft(self) -> None:
        session = self.session()
        app = create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            screen = await self.offer(app, pilot, session, "appearance")
            target = THEME_NAMES[1]
            screen.query_one("#setup-theme", Select).value = target
            await pilot.pause()
            self.assertEqual(session.draft.theme, target)
            self.assertEqual(app.theme, target)

    async def test_finish_later_restores_the_previewed_theme(self) -> None:
        session = self.session()
        app = create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            before = app.theme
            screen = await self.offer(app, pilot, session, "appearance")
            screen.query_one("#setup-theme", Select).value = THEME_NAMES[1]
            await pilot.pause()
            await pilot.press("l")
            await pilot.pause()
            self.assertEqual(app.theme, before)

    async def test_missing_tools_are_listed_with_their_fix(self) -> None:
        session = self.session()
        app = create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            _screen = await self.offer(app, pilot, session, "appearance", _checks((LPUI, GH_AUTH)))
            await self.settle(pilot)
            body = str(app.screen.query_one("#setup-checks-body", Static).render())
            self.assertIn("lpui on PATH", body)
            self.assertIn("Add the folder holding lpui to PATH", body)
            self.assertIn("GitHub CLI login", body)
            self.assertIn("gh auth login", body)
            self.assertIn("✓ git on PATH — ok", body)

    async def test_a_clean_check_marks_every_tool_ok(self) -> None:
        session = self.session()
        app = create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            await self.offer(app, pilot, session, "appearance", _checks(()))
            await self.settle(pilot)
            body = str(app.screen.query_one("#setup-checks-body", Static).render())
            self.assertEqual(body.count("— ok"), 4)

    async def test_recheck_runs_the_probes_again(self) -> None:
        session = self.session()
        calls: list[tuple[HealthFinding, ...]] = [(LPUI,), ()]

        def probe() -> tuple[HealthFinding, ...]:
            return calls.pop(0)

        app = create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            screen = await self.offer(app, pilot, session, "appearance", probe)
            await self.settle(pilot)
            self.assertIn("lpui on PATH", self._checks_body(screen))
            screen.query_one("#setup-recheck").press()
            await self.settle(pilot)
            self.assertIn("✓ lpui on PATH — ok", self._checks_body(screen))
        self.assertEqual(calls, [])

    async def test_a_failed_check_stays_on_the_step_with_the_error(self) -> None:
        session = self.session()

        def broken() -> tuple[HealthFinding, ...]:
            raise RuntimeError("boom")

        app = create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            screen = await self.offer(app, pilot, session, "appearance", broken)
            await self.settle(pilot)
            self.assertIs(screen, app.screen)
            body = self._checks_body(screen)
            self.assertIn("could not run", body)
            self.assertIn("boom", body)

    async def test_the_appearance_step_never_asks_for_a_secret(self) -> None:
        session = self.session()
        app = create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            screen = await self.offer(app, pilot, session, "appearance")
            await self.settle(pilot)
            self.assertEqual(list(screen.query("#setup-panel Input")), [])
            self.assertIn("never asks for or", self._notes(screen))

    def _checks_body(self, screen: Any) -> str:
        return str(screen.query_one("#setup-checks-body", Static).render())

    def _notes(self, screen: Any) -> str:
        return "\n".join(str(item.render()) for item in screen.query(".setup-note"))


if __name__ == "__main__":
    unittest.main()
