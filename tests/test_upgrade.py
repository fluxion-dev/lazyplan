"""Install-method detection and upgrade plumbing (mocked; no network, no installs)."""

import json
import os
import sys
import tempfile
import unittest
import urllib.error
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from lazyplan import cli as cli_mod  # noqa: E402
from lazyplan import upgrade  # noqa: E402
from lazyplan.cli import main  # noqa: E402


class TestDetect(unittest.TestCase):
    def test_pipx_venv_path(self):
        info = upgrade.detect(exe="/home/u/.local/share/pipx/venvs/lazyplan-tui/bin/python")
        self.assertEqual(info.method, upgrade.PIPX)
        self.assertTrue(info.upgradeable)

    def test_plain_venv_is_upgradeable(self):
        with (
            mock.patch.object(upgrade, "_is_editable_install", return_value=False),
            mock.patch.object(upgrade, "_looks_like_source", return_value=False),
        ):
            info = upgrade.detect(
                exe="/home/u/.local/share/lazyplan-venv/bin/python",
                prefix="/home/u/.local/share/lazyplan-venv",
                base_prefix="/usr",
            )
        self.assertEqual(info.method, upgrade.VENV)
        self.assertTrue(info.upgradeable)

    def test_editable_venv_is_source(self):
        with (
            mock.patch.object(upgrade, "_is_editable_install", return_value=True),
            mock.patch.object(upgrade, "_looks_like_source", return_value=False),
        ):
            info = upgrade.detect(
                exe="/repo/.venv/bin/python", prefix="/repo/.venv", base_prefix="/usr"
            )
        self.assertEqual(info.method, upgrade.SOURCE)
        self.assertFalse(info.upgradeable)

    def test_rpm_probe(self):
        with mock.patch.object(upgrade, "_probe", side_effect=[True]):
            info = upgrade.detect(exe="/usr/bin/python3", prefix="/usr", base_prefix="/usr")
        self.assertEqual(info.method, upgrade.RPM)
        self.assertFalse(info.upgradeable)

    def test_deb_probe(self):
        with mock.patch.object(upgrade, "_probe", side_effect=[False, True]):
            info = upgrade.detect(exe="/usr/bin/python3", prefix="/usr", base_prefix="/usr")
        self.assertEqual(info.method, upgrade.DEB)
        self.assertFalse(info.upgradeable)

    def test_source_checkout_layout(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "pyproject.toml").write_text('[project]\nname = "lazyplan-tui"\n')
            exe = str(Path(tmp) / "bin" / "python")
            with mock.patch.object(upgrade, "_probe", return_value=False):
                info = upgrade.detect(exe=exe, prefix="/usr", base_prefix="/usr", cwd=tmp)
        self.assertEqual(info.method, upgrade.SOURCE)
        self.assertFalse(info.upgradeable)

    def test_unknown_layout(self):
        with (
            mock.patch.object(upgrade, "_probe", return_value=False),
            mock.patch.object(upgrade, "_looks_like_source", return_value=False),
        ):
            info = upgrade.detect(exe="/usr/bin/python3", prefix="/usr", base_prefix="/usr")
        self.assertEqual(info.method, upgrade.UNKNOWN)
        self.assertFalse(info.upgradeable)


class TestVersions(unittest.TestCase):
    def test_parse_plain_and_tagged(self):
        self.assertEqual(upgrade.parse_version("0.15.0"), (0, 15, 0))
        self.assertEqual(upgrade.parse_version("v0.15.0"), (0, 15, 0))

    def test_parse_rejects_garbage(self):
        with self.assertRaises(upgrade.UpgradeError):
            upgrade.parse_version("latest")

    def test_latest_follows_redirect(self):
        resp = mock.MagicMock()
        resp.geturl.return_value = "https://github.com/fluxion-dev/lazyplan/releases/tag/v0.16.0"
        ctx = mock.MagicMock()
        ctx.__enter__.return_value = resp
        with mock.patch.object(upgrade.urllib.request, "urlopen", return_value=ctx):
            self.assertEqual(upgrade.latest_version(), "0.16.0")

    def test_latest_offline_raises(self):
        with mock.patch.object(
            upgrade.urllib.request,
            "urlopen",
            side_effect=urllib.error.URLError("no network"),
        ):
            with self.assertRaises(upgrade.UpgradeError):
                upgrade.latest_version()


class TestRunners(unittest.TestCase):
    def test_run_upgrade_rejects_unknown_method(self):
        with self.assertRaises(upgrade.UpgradeError):
            upgrade.run_upgrade(upgrade.InstallInfo(upgrade.RPM, False), "0.16.0")

    def test_run_upgrade_routes_pipx(self):
        with mock.patch.object(upgrade, "upgrade_pipx") as run:
            with mock.patch.object(upgrade, "upgrade_venv") as venv_run:
                upgrade.run_upgrade(PIPX_INFO, "0.16.0")
        run.assert_called_once_with("0.16.0")
        venv_run.assert_not_called()

    def test_run_upgrade_routes_venv(self):
        with mock.patch.object(upgrade, "upgrade_venv") as run:
            upgrade.run_upgrade(VENV_INFO, "0.16.0", "/some/venv/bin/python")
        run.assert_called_once_with("0.16.0", "/some/venv/bin/python")

    def test_pipx_upgrade_first_try_wins(self):
        ok = mock.Mock(returncode=0)
        with (
            mock.patch.object(upgrade.shutil, "which", return_value="/usr/bin/pipx"),
            mock.patch.object(upgrade.subprocess, "run", return_value=ok) as run,
        ):
            upgrade.upgrade_pipx("0.16.0")
        self.assertEqual(run.call_count, 1)

    def test_pipx_upgrade_falls_back_to_force_install(self):
        bad = mock.Mock(returncode=1, stderr="", stdout="nope")
        good = mock.Mock(returncode=0)
        with (
            mock.patch.object(upgrade.shutil, "which", return_value="/usr/bin/pipx"),
            mock.patch.object(upgrade.subprocess, "run", side_effect=[bad, good]) as run,
        ):
            upgrade.upgrade_pipx("0.16.0")
        self.assertEqual(run.call_count, 2)
        self.assertIn("--force", run.call_args[0][0])

    def test_pipx_upgrade_failure_raises(self):
        bad = mock.Mock(returncode=1, stderr="boom", stdout="")
        with (
            mock.patch.object(upgrade.shutil, "which", return_value="/usr/bin/pipx"),
            mock.patch.object(upgrade.subprocess, "run", return_value=bad),
        ):
            with self.assertRaises(upgrade.UpgradeError):
                upgrade.upgrade_pipx("0.16.0")

    def test_pipx_missing_raises(self):
        with mock.patch.object(upgrade.shutil, "which", return_value=None):
            with self.assertRaises(upgrade.UpgradeError):
                upgrade.upgrade_pipx("0.16.0")

    def test_venv_reinstall_runs_venv_pip(self):
        ok = mock.Mock(returncode=0)
        with mock.patch.object(upgrade.subprocess, "run", return_value=ok) as run:
            with mock.patch.object(upgrade.Path, "exists", return_value=True):
                upgrade.upgrade_venv("0.16.0", "/home/u/.local/share/lazyplan-venv/bin/python")
        cmd = run.call_args[0][0]
        self.assertIn("lazyplan-tui==0.16.0", cmd)

    def test_venv_reinstall_failure_raises(self):
        bad = mock.Mock(returncode=1, stderr="boom", stdout="")
        with mock.patch.object(upgrade.subprocess, "run", return_value=bad):
            with mock.patch.object(upgrade.Path, "exists", return_value=True):
                with self.assertRaises(upgrade.UpgradeError):
                    upgrade.upgrade_venv("0.16.0", "/home/u/.local/share/lazyplan-venv/bin/python")


PIPX_INFO = upgrade.InstallInfo(upgrade.PIPX, True, "/home/u/.local/share/pipx/venvs/lazyplan-tui")
VENV_INFO = upgrade.InstallInfo(upgrade.VENV, True, "/home/u/.local/share/lazyplan-venv")
RPM_INFO = upgrade.InstallInfo(upgrade.RPM, False, "system rpm install")


class TestGuards(unittest.TestCase):
    def test_rpm_message_names_package_manager(self):
        msg = upgrade.guard_message(upgrade.InstallInfo(upgrade.RPM, False))
        self.assertIn("dnf", msg)
        self.assertIn("pipx", msg)

    def test_deb_message_names_package_manager(self):
        msg = upgrade.guard_message(upgrade.InstallInfo(upgrade.DEB, False))
        self.assertIn("apt", msg)

    def test_source_message_says_git_pull(self):
        msg = upgrade.guard_message(upgrade.InstallInfo(upgrade.SOURCE, False, "editable"))
        self.assertIn("git pull", msg)

    def test_unknown_message_points_at_installer(self):
        msg = upgrade.guard_message(upgrade.InstallInfo(upgrade.UNKNOWN, False))
        self.assertIn("install.sh", msg)


class TestUpgradeCommand(unittest.TestCase):
    def _run(self, argv: list[str]) -> tuple[int, str, str]:
        out, err = StringIO(), StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_check_reports_without_changing(self):
        with (
            mock.patch.object(cli_mod, "detect", return_value=PIPX_INFO),
            mock.patch.object(cli_mod, "latest_version", return_value="9.9.9"),
            mock.patch.object(cli_mod, "run_upgrade") as run,
        ):
            code, out, _ = self._run(["upgrade", "--check"])
        self.assertEqual(code, 0)
        self.assertIn("9.9.9", out)
        run.assert_not_called()

    def test_check_json_shape(self):
        with (
            mock.patch.object(cli_mod, "detect", return_value=PIPX_INFO),
            mock.patch.object(cli_mod, "latest_version", return_value="9.9.9"),
        ):
            code, out, _ = self._run(["upgrade", "--check", "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(
            (payload["method"], payload["upgraded"]),
            (upgrade.PIPX, False),
        )
        self.assertIn("latest", payload)

    def test_successful_upgrade_reviews_setup_once(self):
        with (
            mock.patch.object(cli_mod, "detect", return_value=PIPX_INFO),
            mock.patch.object(cli_mod, "latest_version", return_value="9.9.9"),
            mock.patch.object(cli_mod, "run_upgrade"),
            mock.patch.object(cli_mod.setup_ui, "stdin_tty", return_value=True),
            mock.patch.object(cli_mod, "_stderr_is_tty", return_value=True),
            mock.patch.object(cli_mod.subprocess, "run") as spawn,
        ):
            code, _out, _ = self._run(["upgrade"])
        self.assertEqual(code, 0)
        spawn.assert_called_once()
        self.assertEqual(spawn.call_args.args[0][1:], ["setup", "--post-upgrade"])

    def test_already_latest(self):
        with (
            mock.patch.object(cli_mod, "detect", return_value=VENV_INFO),
            mock.patch.object(cli_mod, "run_upgrade") as run,
        ):
            with mock.patch.object(
                cli_mod, "latest_version", return_value=cli_mod.package_version()
            ):
                code, out, _ = self._run(["upgrade"])
        self.assertEqual(code, 0)
        self.assertIn("latest release", out)
        run.assert_not_called()

    def test_upgrade_dispatches_runner(self):
        with (
            mock.patch.object(cli_mod, "detect", return_value=PIPX_INFO),
            mock.patch.object(cli_mod, "latest_version", return_value="9.9.9"),
            mock.patch.object(cli_mod, "run_upgrade") as run,
        ):
            code, out, _ = self._run(["upgrade"])
        self.assertEqual(code, 0)
        run.assert_called_once_with(PIPX_INFO, "9.9.9", sys.executable)
        self.assertIn("9.9.9", out)

    def test_upgrade_runner_failure_exits_1(self):
        with (
            mock.patch.object(cli_mod, "detect", return_value=PIPX_INFO),
            mock.patch.object(cli_mod, "latest_version", return_value="9.9.9"),
            mock.patch.object(cli_mod, "run_upgrade", side_effect=upgrade.UpgradeError("boom")),
        ):
            code, _, err = self._run(["upgrade"])
        self.assertEqual(code, 1)
        self.assertIn("boom", err)

    def test_non_upgradeable_method_exits_2(self):
        with (
            mock.patch.object(cli_mod, "detect", return_value=RPM_INFO),
            mock.patch.object(cli_mod, "latest_version", return_value="9.9.9"),
            mock.patch.object(cli_mod, "run_upgrade") as run,
        ):
            with mock.patch.object(
                upgrade.subprocess, "run", side_effect=AssertionError("must not spawn")
            ):
                code, _, err = self._run(["upgrade"])
        self.assertEqual(code, 2)
        self.assertIn("dnf", err)
        run.assert_not_called()

    def test_check_works_for_system_installs(self):
        deb = upgrade.InstallInfo(upgrade.DEB, False, "system deb install")
        with (
            mock.patch.object(cli_mod, "detect", return_value=deb),
            mock.patch.object(cli_mod, "latest_version", return_value="9.9.9"),
        ):
            with mock.patch.object(
                upgrade.subprocess, "run", side_effect=AssertionError("must not spawn")
            ):
                code, out, _ = self._run(["upgrade", "--check"])
        self.assertEqual(code, 0)
        self.assertIn("9.9.9", out)

    def test_offline_upgrade_warns_and_exits_0(self):
        with (
            mock.patch.object(cli_mod, "detect", return_value=PIPX_INFO),
            mock.patch.object(
                cli_mod, "latest_version", side_effect=upgrade.UpgradeError("no network")
            ),
            mock.patch.object(cli_mod, "run_upgrade") as run,
        ):
            code, _, err = self._run(["upgrade"])
        self.assertEqual(code, 0)
        self.assertIn("warning", err)
        self.assertIn("no network", err)
        run.assert_not_called()

    def test_offline_check_json_carries_warning(self):
        with (
            mock.patch.object(cli_mod, "detect", return_value=VENV_INFO),
            mock.patch.object(
                cli_mod, "latest_version", side_effect=upgrade.UpgradeError("no network")
            ),
        ):
            code, out, _ = self._run(["upgrade", "--check", "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertIsNone(payload["latest"])
        self.assertFalse(payload["upgraded"])
        self.assertIn("no network", payload["warning"])

    def test_upgrade_creates_no_db(self):
        cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with (
                    mock.patch.object(cli_mod, "detect", return_value=PIPX_INFO),
                    mock.patch.object(
                        cli_mod, "latest_version", return_value=cli_mod.package_version()
                    ),
                ):
                    code, _, _ = self._run(["upgrade", "--check"])
            finally:
                os.chdir(cwd)
        self.assertEqual(code, 0)
        self.assertEqual(list(Path(tmp).rglob("*.db")), [])


if __name__ == "__main__":
    unittest.main()
