"""Startup health against a real sandboxed home: modal, install, quiet relaunch."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from lazyplan.presentation.setup import health
from lazyplan.presentation.setup.state import SetupState, save_state
from tests.support.home import sandbox_home

try:
    from lazyplan.presentation.tui import create_app
    from lazyplan.presentation.tui.launch import Restart
    from lazyplan.presentation.tui.screens import HealthScreen
except ImportError:  # pragma: no cover - textual not installed
    create_app = HealthScreen = None  # type: ignore[assignment]


@unittest.skipUnless(create_app is not None, "textual not installed")
class HealthEndToEndTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        root = Path(self.tmp.name)
        self.home = root / "home"
        self.home.mkdir()
        sandbox_home(self, self.home)
        tools = root / "bin"
        tools.mkdir()
        for name in ("lpui", "lpui.cmd"):
            shim = tools / name
            shim.write_text("", encoding="utf-8")
            shim.chmod(0o755)
        env = {"PATH": f"{tools}{os.pathsep}{os.environ.get('PATH', '')}", "GH_TOKEN": "t"}
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        save_state(SetupState(placement="home", agents=["claude"], last_version="1.0"), self.home)
        self.db = str(root / "plans.db")
        self.cwd = root

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def launch(self):
        return create_app(self.db, health_check=lambda: health.current(self.cwd, self.home, "1.0"))

    async def settle(self, pilot) -> None:
        await pilot.app.workers.wait_for_complete()
        await pilot.pause()

    async def test_install_and_restart_fixes_the_gaps_for_the_next_launch(self) -> None:
        app = self.launch()
        async with app.run_test(size=(110, 40)) as pilot:
            await self.settle(pilot)
            self.assertIsInstance(app.screen, HealthScreen)
            await pilot.click("#health-install")
            await pilot.pause()
        self.assertEqual(app.return_value, Restart(("Claude Code",)))
        self.assertTrue((self.home / ".claude" / "skills" / "lazyplan" / "SKILL.md").is_file())
        self.assertIn("lpui hook", (self.home / ".claude" / "settings.json").read_text("utf-8"))

        again = self.launch()
        async with again.run_test(size=(110, 40)) as pilot:
            await self.settle(pilot)
            self.assertEqual(len(again.screen_stack), 1)
            self.assertEqual(again.health_controller.report.findings, ())

    async def test_never_ask_keeps_the_next_launch_quiet(self) -> None:
        app = self.launch()
        async with app.run_test(size=(110, 40)) as pilot:
            await self.settle(pilot)
            await pilot.click("#health-never")
            await pilot.pause()

        again = self.launch()
        async with again.run_test(size=(110, 40)) as pilot:
            await self.settle(pilot)
            self.assertEqual(len(again.screen_stack), 1)
            report = again.health_controller.report
            self.assertTrue(report.findings)
            self.assertEqual(report.open, ())


if __name__ == "__main__":
    unittest.main()
