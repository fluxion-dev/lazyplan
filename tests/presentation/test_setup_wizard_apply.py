"""Review lists the exact writes; apply runs off the UI thread."""

from __future__ import annotations

import tempfile
import threading
import unittest
from collections.abc import Iterable
from pathlib import Path
from typing import Any
from unittest import mock

from lazyplan.infrastructure import agent_install
from lazyplan.infrastructure.host_models import HostCatalog
from lazyplan.presentation import setup
from tests.support.home import sandbox_home

try:
    from textual.widgets import Button, Static

    from lazyplan.presentation.tui import create_app
    from lazyplan.presentation.tui.screens import SetupWizardScreen
    from lazyplan.presentation.tui.screens.setup import WizardResult, review_sections
except ImportError:  # pragma: no cover - textual not installed
    create_app = None  # type: ignore[assignment]
    SetupWizardScreen = WizardResult = None  # type: ignore[assignment]
    review_sections = None  # type: ignore[assignment]
    Button = Static = None  # type: ignore[assignment,misc]


def _catalogs(hosts: Iterable[str], _home: Path, _root: Path | None) -> dict[str, HostCatalog]:
    return {host: HostCatalog(host=host, label=host.title()) for host in hosts}


@unittest.skipUnless(create_app is not None, "textual not installed")
class SetupWizardApplyTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        base = Path(self.tmp.name)
        self.home = base / "home"
        self.home.mkdir()
        self.repo = base / "repo"
        self.repo.mkdir()
        (self.repo / ".git").mkdir()
        self.db = str(base / "wizard.db")
        self.state_path = self.home / ".lazyplan" / "setup.json"
        sandbox_home(self, self.home)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def session(self, hosts: list[str] | None = None) -> setup.SetupSession:
        session = setup.SetupSession.load(self.repo, self.home, "1.0", discover=_catalogs)
        session.set_agents(hosts if hosts is not None else ["opencode"])
        session.set_hooks_mode("off")
        for item in session.pending:
            session.set_integration(item.id, "defer")
        return session

    async def offer(
        self, app: Any, pilot: Any, session: setup.SetupSession
    ) -> tuple[Any, list[WizardResult]]:
        results: list[WizardResult] = []
        screen = SetupWizardScreen(session, start="review")
        app.push_screen(screen, results.append)
        await pilot.pause()
        return screen, results

    async def settle(self, pilot: Any) -> None:
        await pilot.pause()
        await pilot.app.workers.wait_for_complete()
        await pilot.pause()

    def sections(self, session: setup.SetupSession) -> dict[str, list[str]]:
        return dict(review_sections(session))

    def status(self, screen: Any) -> str:
        return str(screen.query_one("#setup-apply-status", Static).render())

    async def test_review_names_the_database_templates_and_state(self) -> None:
        session = self.session()
        app = create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            screen, _results = await self.offer(app, pilot, session)
            writes = self.sections(session)["Writes"]
            self.assertIn(str(session.db_path), writes)
            self.assertIn(str(session.db_path.parent / "templates"), writes)
            changes = self.sections(session)["State changes"]
            self.assertTrue(any(str(self.state_path) in line for line in changes))
            text = "\n".join(str(item.render()) for item in screen.query(".setup-list"))
            self.assertIn(str(session.db_path), text)
            self.assertIn("pending wizard marker: cleared", text)

    async def test_review_lists_managed_profiles_for_dropped_hosts(self) -> None:
        session = self.session()
        path = agent_install.profile_paths("global", self.repo, self.home, ["claude"])[0]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            f"# managed by lazyplan: claude scout\n{agent_install.MARKER} claude scout -->\n",
            encoding="utf-8",
        )
        session.state.agents = ["claude", "opencode"]
        removals = self.sections(session)["Removals"]
        self.assertIn(str(path), removals)

    async def test_nothing_is_written_before_apply(self) -> None:
        session = self.session()
        app = create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            _screen, results = await self.offer(app, pilot, session)
            self.assertFalse(Path(session.db_path).exists())
            self.assertFalse(self.state_path.exists())
            await pilot.press("l")
            await pilot.pause()
        self.assertFalse(results[-1].applied)
        self.assertFalse(Path(session.db_path).exists())
        self.assertFalse(self.state_path.exists())

    async def test_apply_writes_the_files_and_returns_a_restart_payload(self) -> None:
        session = self.session()
        app = create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            screen, results = await self.offer(app, pilot, session)
            screen.query_one("#setup-next", Button).press()
            await self.settle(pilot)
            self.assertTrue(Path(session.db_path).is_file())
            self.assertTrue(self.state_path.is_file())
            self.assertIn("Setup applied", self.status(screen))
            self.assertEqual(str(screen.query_one("#setup-next", Button).label), "Close")
            self.assertEqual(results, [])
            screen.query_one("#setup-next", Button).press()
            await pilot.pause()
        result = results[-1]
        self.assertIsInstance(result, WizardResult)
        self.assertTrue(result.applied)
        self.assertEqual(result.hosts, ("opencode",))
        self.assertTrue(result.profiles)
        self.assertTrue(result.restart)
        self.assertEqual(result.result["db"], str(session.db_path))

    async def test_apply_without_skills_or_agents_needs_no_restart(self) -> None:
        session = self.session(hosts=[])
        session.set_skills_enabled(False)
        app = create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            screen, results = await self.offer(app, pilot, session)
            screen.query_one("#setup-next", Button).press()
            await self.settle(pilot)
            screen.query_one("#setup-next", Button).press()
            await pilot.pause()
        self.assertEqual(results[-1].hosts, ())
        self.assertFalse(results[-1].restart)

    async def test_apply_runs_off_the_ui_thread(self) -> None:
        session = self.session()
        threads: list[threading.Thread] = []
        real_apply = session.apply

        def tracked(write: Any = None) -> dict[str, Any]:
            threads.append(threading.current_thread())
            return real_apply(write)

        app = create_app(self.db)
        with mock.patch.object(session, "apply", side_effect=tracked):
            async with app.run_test(size=(120, 40)) as pilot:
                screen, _results = await self.offer(app, pilot, session)
                screen.query_one("#setup-next", Button).press()
                await self.settle(pilot)
        self.assertTrue(threads)
        self.assertIsNot(threads[0], threading.main_thread())

    async def test_a_failed_apply_stays_on_the_step_with_the_error(self) -> None:
        session = self.session()
        app = create_app(self.db)
        with mock.patch.object(session, "apply", side_effect=RuntimeError("disk full")):
            async with app.run_test(size=(120, 40)) as pilot:
                screen, results = await self.offer(app, pilot, session)
                screen.query_one("#setup-next", Button).press()
                await self.settle(pilot)
                self.assertIs(screen, app.screen)
                body = self.status(screen)
                self.assertIn("Apply failed", body)
                self.assertIn("disk full", body)
                self.assertEqual(str(screen.query_one("#setup-next", Button).label), "Apply")
                self.assertFalse(self.state_path.exists())
        self.assertEqual(results, [])

    async def test_validation_stops_apply_before_it_starts(self) -> None:
        session = self.session()
        session.set_hooks_mode("sometimes")
        app = create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            screen, _results = await self.offer(app, pilot, session)
            screen.query_one("#setup-next", Button).press()
            await self.settle(pilot)
            self.assertIs(screen, app.screen)
            errors = screen.query_one("#setup-errors", Static)
            self.assertTrue(errors.display)
            self.assertIn("hooks mode", str(errors.render()))
            self.assertFalse(self.state_path.exists())

    async def test_finish_later_after_apply_still_returns_the_payload(self) -> None:
        session = self.session()
        app = create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            screen, results = await self.offer(app, pilot, session)
            screen.query_one("#setup-next", Button).press()
            await self.settle(pilot)
            await pilot.press("l")
            await pilot.pause()
        self.assertTrue(results[-1].applied)

    async def test_escape_after_apply_closes_with_the_payload(self) -> None:
        session = self.session()
        app = create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            screen, results = await self.offer(app, pilot, session)
            screen.query_one("#setup-next", Button).press()
            await self.settle(pilot)
            await pilot.press("escape")
            await pilot.pause()
            self.assertNotIsInstance(app.screen, SetupWizardScreen)
        self.assertTrue(results[-1].applied)


if __name__ == "__main__":
    unittest.main()
