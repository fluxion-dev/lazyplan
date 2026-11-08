"""Update screen and launch-apply behavior (headless, no network or installs)."""

from __future__ import annotations

import importlib
import os
import tempfile
import unittest
from unittest import mock

from lazyplan.infrastructure import update_stage
from lazyplan.infrastructure.upgrade import PIPX, RPM, SOURCE, InstallInfo
from lazyplan.store import Store
from tests.support.home import sandbox_home
from tests.support.pilot import settle

try:
    tui_mod = importlib.import_module("lazyplan.presentation.tui.app")
    launch_mod = importlib.import_module("lazyplan.presentation.tui.launch")
    screen_mod = importlib.import_module("lazyplan.presentation.tui.screens.update")
    updates_mod = importlib.import_module("lazyplan.presentation.tui.controllers.updates")
except ImportError:  # stdlib-only interpreter
    tui_mod = None  # type: ignore[assignment]
    launch_mod = None  # type: ignore[assignment]
    screen_mod = None  # type: ignore[assignment]
    updates_mod = None  # type: ignore[assignment]


STAGED = update_stage.StagedUpdate(
    "9.9.9",
    PIPX,
    "lazyplan_tui-9.9.9-py3-none-any.whl",
    "https://files.pythonhosted.org/packages/x/w.whl",
    "a" * 64,
    10,
    1000.0,
)


@unittest.skipUnless(tui_mod is not None and tui_mod._TEXTUAL_OK, "textual not installed")
class TestUpdateScreen(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        sandbox_home(self, os.path.join(self.tmp.name, "home"))
        os.makedirs(os.environ["HOME"], exist_ok=True)
        self.db = os.path.join(self.tmp.name, "t.db")
        Store(self.db).add_plan("P")
        self.app = tui_mod.create_app(self.db)

    async def asyncTearDown(self):
        self.tmp.cleanup()

    async def _open(self, info: InstallInfo):

        from lazyplan.presentation.tui.screens.update import UpdateScreen

        screen = UpdateScreen("0.27.2", "9.9.9", info)
        self.app.push_screen(screen)
        await self.app.workers.wait_for_complete()
        return screen

    async def test_upgradeable_shows_download_and_later(self):
        async with self.app.run_test() as pilot:
            screen = await self._open(InstallInfo(PIPX, True))
            await pilot.pause()
            self.assertTrue(screen.query_one("#update-download"))
            self.assertTrue(screen.query_one("#update-later"))
            self.assertIn("Download now", str(screen.query_one("#update-body").render()))

    async def test_later_dismisses_without_staging(self):
        from lazyplan.presentation.tui.screens.update import UpdateScreen

        async with self.app.run_test() as pilot:
            screen = UpdateScreen("0.27.2", "9.9.9", InstallInfo(PIPX, True))
            self.app.push_screen(screen)
            await pilot.pause()
            with mock.patch.object(screen_mod, "stage_update") as stage:
                screen.query_one("#update-later").press()
                await pilot.pause()
            stage.assert_not_called()
            self.assertNotIsInstance(self.app.screen, UpdateScreen)

    async def test_download_reports_ready(self):
        from textual.widgets import Button, Static

        async with self.app.run_test() as pilot:
            screen = await self._open(InstallInfo(PIPX, True))
            await pilot.pause()
            with mock.patch.object(screen_mod, "stage_update", return_value=STAGED) as stage:
                screen.query_one("#update-download", Button).press()
                await self.app.workers.wait_for_complete()
                await pilot.pause()
            stage.assert_called_once_with("9.9.9", PIPX, installed="0.27.2")
            self.assertIn(
                "Downloaded v9.9.9", str(screen.query_one("#update-body", Static).render())
            )
            self.assertFalse(screen.query_one("#update-download", Button).display)
            self.assertEqual(screen.query_one("#update-later", Button).label, "Close")

    async def test_windows_download_offers_restart(self) -> None:
        from textual.widgets import Button, Static

        from lazyplan.presentation.tui.screens.update import UpdateScreen

        async with self.app.run_test() as pilot:
            screen = UpdateScreen("0.27.2", "9.9.9", InstallInfo(PIPX, True), windows=True)
            self.app.push_screen(screen)
            await pilot.pause()
            with mock.patch.object(screen_mod, "stage_update", return_value=STAGED):
                screen.query_one("#update-download", Button).press()
                await self.app.workers.wait_for_complete()
                await settle(pilot)
            self.assertTrue(screen.query_one("#update-restart", Button).display)
            self.assertIn(
                "Restart now",
                str(screen.query_one("#update-body", Static).render()),
            )

    async def test_windows_restart_spawns_the_helper_and_exits(self) -> None:
        from textual.widgets import Button

        from lazyplan.presentation.tui.screens.update import UpdateScreen

        async with self.app.run_test() as pilot:
            screen = UpdateScreen("0.27.2", "9.9.9", InstallInfo(PIPX, True), windows=True)
            self.app.push_screen(screen)
            await pilot.pause()
            plan = mock.Mock()
            with (
                mock.patch.object(screen_mod, "stage_update", return_value=STAGED),
                mock.patch.object(screen_mod, "build_apply_plan", return_value=plan) as build,
                mock.patch.object(screen_mod, "spawn_windows_apply") as spawn,
                mock.patch.object(self.app, "exit") as exit_app,
            ):
                screen.query_one("#update-download", Button).press()
                await self.app.workers.wait_for_complete()
                await pilot.pause()
                screen.query_one("#update-restart", Button).press()
                await pilot.pause()
            build.assert_called_once()
            spawn.assert_called_once()
            self.assertEqual(spawn.call_args.kwargs["parent_pid"], os.getpid())
            exit_app.assert_called_once()

    async def test_download_failure_offers_retry(self):
        from textual.widgets import Button, Static

        async with self.app.run_test() as pilot:
            screen = await self._open(InstallInfo(PIPX, True))
            await pilot.pause()
            with mock.patch.object(
                screen_mod, "stage_update", side_effect=update_stage.StageError("offline")
            ):
                screen.query_one("#update-download", Button).press()
                await self.app.workers.wait_for_complete()
                await pilot.pause()
            body = str(screen.query_one("#update-body", Static).render())
            self.assertIn("Download failed", body)
            self.assertIn("offline", body)
            self.assertEqual(screen.query_one("#update-download", Button).label, "Retry download")

    async def test_guard_hides_download(self):
        async with self.app.run_test() as pilot:
            screen = await self._open(InstallInfo(RPM, False))
            await pilot.pause()
            self.assertEqual(len(screen.query("#update-download")), 0)
            self.assertIn("package manager", str(screen.query_one("#update-body").render()))

    async def test_u_opens_the_screen(self):
        async with self.app.run_test() as pilot:
            self.app._update_latest = "9.9.9"
            self.app._update_info = InstallInfo(PIPX, True)
            await pilot.press("U")
            await pilot.pause()
            self.assertEqual(self.app.screen.__class__.__name__, "UpdateScreen")

    async def test_source_guard_is_used(self):
        async with self.app.run_test() as pilot:
            screen = await self._open(InstallInfo(SOURCE, False, "checkout"))
            await pilot.pause()
            self.assertIn("git pull", str(screen.query_one("#update-body").render()))

    async def test_equal_latest_hides_download(self):
        from lazyplan.presentation.tui.screens.update import UpdateScreen

        async with self.app.run_test() as pilot:
            screen = UpdateScreen("0.27.2", "0.27.2", InstallInfo(PIPX, True))
            self.app.push_screen(screen)
            await pilot.pause()
            self.assertEqual(len(screen.query("#update-download")), 0)
            self.assertIn("already on the latest", str(screen.query_one("#update-body").render()))

    async def test_older_latest_hides_download(self):
        from lazyplan.presentation.tui.screens.update import UpdateScreen

        async with self.app.run_test() as pilot:
            screen = UpdateScreen("0.28.0", "0.27.2", InstallInfo(PIPX, True))
            self.app.push_screen(screen)
            await pilot.pause()
            self.assertEqual(len(screen.query("#update-download")), 0)
            self.assertIn("Downgrades are disabled", str(screen.query_one("#update-body").render()))

    async def test_cached_older_notice_does_not_open_the_screen(self):
        with mock.patch.object(self.app.update_controller, "tick"):
            async with self.app.run_test() as pilot:
                self.app._update_latest = ""
                with (
                    mock.patch.object(updates_mod, "cached_latest", return_value="0.27.1"),
                    mock.patch.object(updates_mod, "package_version", return_value="0.28.0"),
                    mock.patch.object(self.app, "notify") as toast,
                ):
                    self.app.action_update_prompt()
                    await pilot.pause()
                toast.assert_called_once()
                self.assertNotEqual(self.app.screen.__class__.__name__, "UpdateScreen")


@unittest.skipUnless(tui_mod is not None and tui_mod._TEXTUAL_OK, "textual not installed")
class TestLaunchApply(unittest.TestCase):
    def test_applied_reexecs_or_warns(self):
        with (
            mock.patch.object(launch_mod, "apply_on_launch", return_value=("applied", "9.9.9")),
            mock.patch.object(launch_mod.os, "execv", side_effect=OSError("no exec")),
            mock.patch.object(tui_mod, "create_app") as create,
        ):
            tui_mod.run("t.db")
        self.assertIn("installed", create.call_args[0][1])

    def test_apply_error_reaches_the_app(self):
        with (
            mock.patch.object(launch_mod, "apply_on_launch", return_value=("error", "boom")),
            mock.patch.object(tui_mod, "create_app") as create,
        ):
            tui_mod.run("t.db")
        self.assertIn("boom", create.call_args[0][1])

    def test_applying_launch_exits_without_starting_the_app(self):
        with (
            mock.patch.object(launch_mod, "apply_on_launch", return_value=("applying", "/logs/x")),
            mock.patch.object(tui_mod, "create_app") as create,
        ):
            code = tui_mod.run("t.db")
        self.assertEqual(code, 0)
        create.assert_not_called()

    def test_prior_failure_is_shown_once(self):
        with (
            mock.patch.object(launch_mod, "apply_on_launch", return_value=("none", "")),
            mock.patch.object(launch_mod, "read_failure", return_value="old failure"),
            mock.patch.object(launch_mod, "clear_failure") as clear,
            mock.patch.object(tui_mod, "create_app") as create,
        ):
            tui_mod.run("t.db")
        self.assertIn("old failure", create.call_args[0][1])
        clear.assert_called_once()
