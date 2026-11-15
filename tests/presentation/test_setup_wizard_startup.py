"""Startup and palette wiring: the wizard opens when due, health waits."""

from __future__ import annotations

import contextlib
import os
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from lazyplan.presentation.setup.state import SetupState, save_state
from lazyplan.presentation.setup.triggers import FRESH, INTEGRATIONS, PROFILES, REQUEST, VERSION
from tests.support.home import sandbox_home

try:
    from textual.app import ComposeResult
    from textual.screen import Screen
    from textual.widgets import Static

    from lazyplan.presentation.tui import create_app
    from lazyplan.presentation.tui.controllers.setup import current
    from lazyplan.presentation.tui.screens import HealthScreen
except ImportError:  # pragma: no cover - textual not installed
    create_app = None  # type: ignore[assignment]


if create_app is not None:

    class FakeWizardScreen(Screen[dict[str, Any] | None]):
        """Stand-in for lane M68's screen: same constructor, plain body."""

        def __init__(self, session: Any, need: Any) -> None:
            super().__init__()
            self.session = session
            self.need = need
            self.applied = False

        def compose(self) -> ComposeResult:
            yield Static(f"setup wizard: {self.need.reason}", id="fake-wizard")

    def fake_screen(launch: Any) -> FakeWizardScreen:
        return FakeWizardScreen(launch.session, launch.need)


@unittest.skipUnless(create_app is not None, "textual not installed")
class SetupStartupTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        root = Path(self.tmp.name)
        self.home = root / "home"
        self.home.mkdir()
        self.repo = root / "repo"
        self.repo.mkdir()
        sandbox_home(self, self.home)
        self.old_db = os.environ.pop("LAZYPLAN_DB", None)
        self.db = str(root / "plans.db")
        discovery = mock.patch("lazyplan.infrastructure.host_models.discover_all", return_value={})
        discovery.start()
        self.addCleanup(discovery.stop)

    def tearDown(self) -> None:
        if self.old_db is not None:
            os.environ["LAZYPLAN_DB"] = self.old_db
        self.tmp.cleanup()

    def state(self, **fields: Any) -> None:
        save_state(SetupState(placement="home", agents=[], **fields), self.home)

    @contextlib.contextmanager
    def probes(self, pending: tuple[object, ...] = (), drift: bool = False) -> Any:
        """Answer the two live probes instead of inspecting this checkout."""
        with (
            mock.patch("lazyplan.presentation.setup.triggers._pending_items", return_value=pending),
            mock.patch("lazyplan.presentation.setup.triggers._profile_drift", return_value=drift),
        ):
            yield

    def launch(self, version: str = "1.0") -> Any:
        app = create_app(self.db, wizard_check=current(self.repo, self.home, version))
        app.setup_controller.screen_factory = fake_screen
        return app

    async def settle(self, pilot: Any) -> None:
        for _ in range(3):
            await pilot.app.workers.wait_for_complete()
            await pilot.pause()

    async def test_a_fresh_install_opens_the_wizard_after_the_first_paint(self) -> None:
        app = self.launch()
        async with app.run_test(size=(120, 40)) as pilot:
            await self.settle(pilot)
            self.assertIsInstance(app.screen, FakeWizardScreen)
            self.assertEqual(app.screen.need.reason, FRESH)
            self.assertTrue(app.setup_controller.pending)
            self.assertIsNotNone(app.screen.session)
            self.assertEqual(len(app.screen_stack), 2)

    async def test_a_version_change_opens_the_wizard_with_that_reason(self) -> None:
        self.state(last_version="1.0", wizard_completed="0.9")
        app = self.launch()
        async with app.run_test(size=(120, 40)) as pilot:
            await self.settle(pilot)
            self.assertIsInstance(app.screen, FakeWizardScreen)
            self.assertEqual(app.screen.need.reason, VERSION)

    async def test_pending_integrations_open_the_wizard(self) -> None:
        self.state(last_version="1.0", wizard_completed="1.0")
        with self.probes(pending=("item",)):
            app = self.launch()
            async with app.run_test(size=(120, 40)) as pilot:
                await self.settle(pilot)
                self.assertIsInstance(app.screen, FakeWizardScreen)
                self.assertEqual(app.screen.need.reason, INTEGRATIONS)

    async def test_profile_drift_opens_the_wizard(self) -> None:
        self.state(last_version="1.0", wizard_completed="1.0")
        with self.probes(drift=True):
            app = self.launch()
            async with app.run_test(size=(120, 40)) as pilot:
                await self.settle(pilot)
                self.assertIsInstance(app.screen, FakeWizardScreen)
                self.assertEqual(app.screen.need.reason, PROFILES)

    async def test_a_clean_state_stays_on_the_tree(self) -> None:
        self.state(last_version="1.0", wizard_completed="1.0")
        with self.probes():
            app = self.launch()
            async with app.run_test(size=(120, 40)) as pilot:
                await self.settle(pilot)
                self.assertEqual(len(app.screen_stack), 1)
                self.assertFalse(app.setup_controller.pending)

    async def test_the_key_opens_the_wizard_on_request(self) -> None:
        self.state(last_version="1.0", wizard_completed="1.0")
        with self.probes():
            app = self.launch()
            async with app.run_test(size=(120, 40)) as pilot:
                await self.settle(pilot)
                self.assertEqual(len(app.screen_stack), 1)
                await pilot.press("S")
                await self.settle(pilot)
                self.assertIsInstance(app.screen, FakeWizardScreen)
                self.assertEqual(app.screen.need.reason, REQUEST)

    async def test_the_palette_command_opens_the_wizard(self) -> None:
        self.state(last_version="1.0", wizard_completed="1.0")
        with self.probes():
            app = self.launch()
            async with app.run_test(size=(120, 40)) as pilot:
                await self.settle(pilot)
                self.assertEqual(len(app.screen_stack), 1)
                app.action_open_setup()
                await self.settle(pilot)
                self.assertIsInstance(app.screen, FakeWizardScreen)
                self.assertEqual(app.screen.need.reason, REQUEST)

    async def test_the_startup_health_prompt_waits_for_the_wizard(self) -> None:
        from lazyplan.presentation.setup import health

        self.state(last_version="1.0", wizard_completed="1.0")
        with self.probes(pending=("item",)):
            app = create_app(
                self.db,
                health_check=lambda: health.current(self.repo, self.home, "1.0"),
                wizard_check=current(self.repo, self.home, "1.0"),
            )
            app.setup_controller.screen_factory = fake_screen
            async with app.run_test(size=(120, 40)) as pilot:
                await self.settle(pilot)
                self.assertIsInstance(app.screen, FakeWizardScreen)
                self.assertFalse(any(isinstance(s, HealthScreen) for s in app.screen_stack))
                self.assertIsNotNone(app.health_controller.report)

    async def test_a_completed_apply_refreshes_health_and_the_tree(self) -> None:
        app = self.launch()
        async with app.run_test(size=(120, 40)) as pilot:
            await self.settle(pilot)
            self.assertIsInstance(app.screen, FakeWizardScreen)
            with (
                mock.patch.object(app.health_controller, "refresh") as refresh,
                mock.patch.object(app, "refresh_all") as refreshed,
            ):
                app.screen.dismiss({"applied": True})
                await self.settle(pilot)
            refresh.assert_called_once()
            refreshed.assert_called_once()
            self.assertFalse(app.setup_controller.pending)
            self.assertEqual(len(app.screen_stack), 1)

    async def test_finishing_later_keeps_the_wizard_pending(self) -> None:
        app = self.launch()
        async with app.run_test(size=(120, 40)) as pilot:
            await self.settle(pilot)
            app.screen.dismiss(None)
            await self.settle(pilot)
            self.assertEqual(len(app.screen_stack), 1)
            self.assertTrue(app.setup_controller.pending)

    async def test_a_missing_screen_class_leaves_the_app_running(self) -> None:
        app = self.launch()
        app.setup_controller.screen_factory = mock.Mock(side_effect=ImportError("no screen"))
        async with app.run_test(size=(120, 40)) as pilot:
            await self.settle(pilot)
            self.assertEqual(len(app.screen_stack), 1)


if __name__ == "__main__":
    unittest.main()
