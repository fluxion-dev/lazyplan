"""Update-availability notice: text builder plus TUI surface (mocked network)."""

import argparse
import importlib
import os
import tempfile
import time
import unittest
from unittest import mock

from lazyplan import upgrade
from lazyplan.store import Store
from tests.support.home import sandbox_home

try:
    tui_mod = importlib.import_module("lazyplan.tui.app")
except ImportError:  # stdlib-only interpreter: no textual, no screens
    tui_mod = None  # type: ignore[assignment]

cli_mod = importlib.import_module("lazyplan.cli.main")


class TestNoticeText(unittest.TestCase):
    def test_pipx_names_upgrade(self):
        info = upgrade.InstallInfo(upgrade.PIPX, True)
        text = upgrade.notice_text(info, "0.15.0", "0.16.0")
        assert text is not None
        self.assertIn("0.16.0", text)
        self.assertIn("lpui upgrade", text)

    def test_current_returns_none(self):
        info = upgrade.InstallInfo(upgrade.PIPX, True)
        self.assertIsNone(upgrade.notice_text(info, "0.16.0", "0.16.0"))
        self.assertIsNone(upgrade.notice_text(info, "0.17.0", "0.16.0"))

    def test_unparseable_returns_none(self):
        info = upgrade.InstallInfo(upgrade.PIPX, True)
        self.assertIsNone(upgrade.notice_text(info, "bogus", "0.16.0"))

    def test_source_names_git_pull(self):
        info = upgrade.InstallInfo(upgrade.SOURCE, False)
        text = upgrade.notice_text(info, "0.15.0", "0.16.0")
        assert text is not None
        self.assertIn("git pull", text)
        self.assertNotIn("lpui upgrade", text)

    def test_system_names_package_manager(self):
        for method in (upgrade.RPM, upgrade.DEB):
            info = upgrade.InstallInfo(method, False)
            text = upgrade.notice_text(info, "0.15.0", "0.16.0")
            assert text is not None
            self.assertIn("package manager", text)


class TestUpdateCache(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = os.path.join(self.tmp.name, "home")
        os.makedirs(self.home, exist_ok=True)
        sandbox_home(self, self.home)

    def test_roundtrip_and_ttl(self):
        upgrade.remember_latest("9.9.9", now=1_000)
        self.assertEqual(upgrade.cached_latest(), "9.9.9")
        self.assertEqual(upgrade.cached_latest(max_age=10, now=1_005), "9.9.9")
        self.assertIsNone(upgrade.cached_latest(max_age=10, now=1_020))

    def test_bad_cache_is_ignored(self):
        path = upgrade.update_cache_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{not json", encoding="utf-8")
        self.assertIsNone(upgrade.cached_latest())

    def test_environment_can_disable_checks(self):
        with mock.patch.dict(os.environ, {upgrade.NO_UPDATE_ENV: "1"}):
            self.assertFalse(upgrade.update_check_enabled())
        with mock.patch.dict(os.environ, {upgrade.NO_UPDATE_ENV: ""}):
            self.assertTrue(upgrade.update_check_enabled())


class TestNoticeSkipsAgentCalls(unittest.TestCase):
    def _checked(self, **fields: object) -> bool:
        args = argparse.Namespace(**{"json": False, "version": False, "porcelain": False, **fields})
        with (
            mock.patch.object(cli_mod, "latest_version", return_value="0.0.1") as latest,
            mock.patch.dict(os.environ, {"LAZYPLAN_PORCELAIN": ""}),
        ):
            cli_mod._maybe_notice_update(args)
        return latest.called

    def test_agent_facing_calls_never_reach_the_network(self):
        for fields in ({"cmd": "hook"}, {"cmd": "mcp"}, {"cmd": "list", "porcelain": True}):
            with self.subTest(fields=fields):
                self.assertFalse(self._checked(**fields))

    def test_human_commands_use_cache_only(self):
        self.assertFalse(self._checked(cmd="list"))


@unittest.skipUnless(tui_mod is not None and tui_mod._TEXTUAL_OK, "textual not installed")
class TestTuiNotice(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        sandbox_home(self, os.path.join(self.tmp.name, "home"))
        os.makedirs(os.environ["HOME"], exist_ok=True)
        self.db = os.path.join(self.tmp.name, "t.db")
        Store(self.db).add_plan("P")
        self.app = tui_mod.create_app(self.db)

    async def asyncTearDown(self):
        self.tmp.cleanup()

    async def _wait_for_notice(self, pilot, app):
        for _ in range(100):
            if app._update_notice is not None:
                return
            await pilot.pause()
        self.fail("update notice never landed")

    async def test_outdated_shows_statusbar_and_toast_once(self):
        from textual.widgets import Label

        info = upgrade.InstallInfo(upgrade.PIPX, True)
        with (
            mock.patch.object(tui_mod, "refresh_update", return_value="9.9.9") as refresh,
            mock.patch.object(tui_mod, "detect", return_value=info),
            mock.patch.object(tui_mod, "package_version", return_value="0.16.0"),
            mock.patch.object(self.app, "notify") as toast,
        ):
            async with self.app.run_test() as pilot:
                await self._wait_for_notice(pilot, self.app)
                await pilot.pause()
                bar = self.app.query_one("#status", Label)
                self.assertIn("update v9.9.9", str(bar.content))
                self.assertEqual(refresh.call_count, 1)
                self.app._announce_update(self.app._update_notice or "")
                self.app._announce_update(self.app._update_notice or "")
                self.assertEqual(toast.call_count, 1)
                notice = toast.call_args[0][0]
                self.assertIn("9.9.9", notice)
                self.assertIn("lpui upgrade", notice)

    async def test_offline_stays_silent(self):
        with mock.patch.object(tui_mod, "refresh_update", return_value=None):
            async with self.app.run_test() as pilot:
                await pilot.pause()
                await pilot.pause()
                self.assertIsNone(self.app._update_notice)
                self.assertFalse(self.app._update_toasted)

    async def test_current_stays_silent(self):
        info = upgrade.InstallInfo(upgrade.PIPX, True)
        with (
            mock.patch.object(tui_mod, "refresh_update", return_value=tui_mod.package_version()),
            mock.patch.object(tui_mod, "detect", return_value=info),
        ):
            async with self.app.run_test() as pilot:
                await pilot.pause()
                await pilot.pause()
                self.assertIsNone(self.app._update_notice)

    async def test_chip_clears_when_current(self):
        from textual.widgets import Label

        info = upgrade.InstallInfo(upgrade.PIPX, True)
        with mock.patch.object(tui_mod, "refresh_update", return_value=None):
            async with self.app.run_test() as pilot:
                await pilot.pause()
                self.app._announce_update("update v9.9.9 available", "9.9.9", info)
                await pilot.pause()
                self.assertIn("update v9.9.9", str(self.app.query_one("#status", Label).content))
                with (
                    mock.patch.object(tui_mod, "package_version", return_value="9.9.9"),
                    mock.patch.object(tui_mod, "detect", return_value=info),
                ):
                    self.app._apply_update("9.9.9")
                await pilot.pause()
                self.assertIsNone(self.app._update_notice)
                self.assertEqual(self.app._update_latest, "")
                self.assertNotIn("update v9.9.9", str(self.app.query_one("#status", Label).content))

    async def test_update_timer_stops_on_unmount(self):
        with mock.patch.object(tui_mod, "refresh_update", return_value=None):
            async with self.app.run_test() as pilot:
                await pilot.pause()
                self.assertIsNotNone(self.app._update_timer)
        self.assertIsNone(self.app._update_timer)

    async def test_update_checks_never_stack(self):
        with mock.patch.object(tui_mod, "refresh_update", return_value=None):
            async with self.app.run_test() as pilot:
                await pilot.pause()
                self.app._update_checking = True
                with mock.patch.object(self.app, "run_worker") as worker:
                    self.app._update_tick()
                worker.assert_not_called()

    async def test_idle_tick_starts_one_worker(self):
        with mock.patch.object(tui_mod, "refresh_update", return_value=None):
            async with self.app.run_test() as pilot:
                await pilot.pause()
                self.app._update_checking = False
                with mock.patch.object(self.app, "run_worker") as worker:
                    self.app._update_tick()
                worker.assert_called_once()


class TestCliNotice(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = os.path.join(self.tmp.name, "home")
        os.makedirs(self.home, exist_ok=True)
        sandbox_home(self, self.home)

    def _run(self, argv: list[str]) -> tuple[int, str, str]:
        import io
        import warnings
        from contextlib import redirect_stderr, redirect_stdout

        from lazyplan.cli import main

        out, err = io.StringIO(), io.StringIO()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            with redirect_stdout(out), redirect_stderr(err):
                code = main(argv)
        return code, out.getvalue(), err.getvalue()

    def _db_argv(self, tmp: str, extra: list[str]) -> list[str]:
        return ["--db", os.path.join(tmp, "t.db"), *extra]

    def test_cached_outdated_lists_notice_on_stderr(self):
        info = upgrade.InstallInfo(upgrade.PIPX, True)
        upgrade.remember_latest("9.9.9", now=time.time())
        with (
            mock.patch.object(cli_mod, "latest_version", side_effect=AssertionError("network")),
            mock.patch.object(cli_mod, "detect", return_value=info),
        ):
            code, out, err = self._run(["--db", os.path.join(self.tmp.name, "t.db"), "list"])
        self.assertEqual(code, 0)
        self.assertIn("9.9.9", err)
        self.assertIn("lpui upgrade", err)
        self.assertNotIn("9.9.9", out)

    def test_json_stays_silent(self):
        import json

        info = upgrade.InstallInfo(upgrade.PIPX, True)
        upgrade.remember_latest("9.9.9", now=time.time())
        with (
            mock.patch.object(cli_mod, "latest_version", side_effect=AssertionError("network")),
            mock.patch.object(cli_mod, "detect", return_value=info),
        ):
            code, out, err = self._run(
                ["--db", os.path.join(self.tmp.name, "t.db"), "list", "--json"]
            )
        self.assertEqual(code, 0)
        self.assertEqual(err, "")
        json.loads(out)

    def test_version_and_upgrade_skip_notice(self):
        info = upgrade.InstallInfo(upgrade.PIPX, True)
        with (
            mock.patch.object(cli_mod, "latest_version", return_value="9.9.9"),
            mock.patch.object(cli_mod, "detect", return_value=info),
        ):
            _, _, err_version = self._run(["--version"])
            self.assertEqual(err_version, "")
            _, _, err_upgrade = self._run(["upgrade", "--check"])
            self.assertNotIn("available", err_upgrade)

    def test_offline_cli_stays_silent(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(
                cli_mod, "latest_version", side_effect=upgrade.UpgradeError("down")
            ):
                code, _, err = self._run(self._db_argv(tmp, ["list"]))
        self.assertEqual(code, 0)
        self.assertEqual(err, "")


if __name__ == "__main__":
    unittest.main()
