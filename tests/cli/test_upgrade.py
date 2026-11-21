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

from lazyplan.infrastructure import update_log, update_stage, upgrade
from lazyplan.presentation.cli import main
from lazyplan.presentation.cli.commands import admin as cli_mod
from tests.support.home import sandbox_home


class TestDetect(unittest.TestCase):
    def test_pipx_venv_path(self):
        info = upgrade.detect(exe="/home/u/.local/share/pipx/venvs/lazyplan-tui/bin/python")
        self.assertEqual(info.method, upgrade.PIPX)
        self.assertTrue(info.upgradeable)

    def test_pipx_venv_path_on_windows_keeps_the_drive(self):
        exe = "C:/Users/u/pipx/venvs/lazyplan-tui/Scripts/python.exe"
        self.assertEqual(
            upgrade._looks_like_pipx(exe).lower(), "c:/users/u/pipx/venvs/lazyplan-tui"
        )

    def test_uv_tool_venv_is_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            venv = Path(tmp) / "uv" / "tools" / "lazyplan-tui"
            venv.mkdir(parents=True)
            (venv / "uv-receipt.toml").write_text(
                '[tool]\nrequirements = [{ name = "lazyplan-tui" }]\n', encoding="utf-8"
            )
            info = upgrade.detect(
                exe=str(venv / "bin" / "python"),
                prefix=str(venv),
                base_prefix="/usr",
                cwd=tmp,
            )
        self.assertEqual(info.method, upgrade.UV)
        self.assertTrue(info.upgradeable)
        self.assertEqual(info.detail, venv.as_posix())

    def test_uv_tool_venv_wins_over_a_source_checkout(self):
        with tempfile.TemporaryDirectory() as tmp:
            venv = Path(tmp) / "uv" / "tools" / "lazyplan-tui"
            venv.mkdir(parents=True)
            (venv / "uv-receipt.toml").write_text(
                '[tool]\nrequirements = [{ name = "lazyplan-tui" }]\n', encoding="utf-8"
            )
            (Path(tmp) / "pyproject.toml").write_text(
                '[project]\nname = "lazyplan-tui"\n', encoding="utf-8"
            )
            info = upgrade.detect(
                exe=str(venv / "bin" / "python"),
                prefix=str(venv),
                base_prefix="/usr",
                cwd=tmp,
            )
        self.assertEqual(info.method, upgrade.UV)

    def test_uv_receipt_for_another_package_is_not_uv(self):
        with tempfile.TemporaryDirectory() as tmp:
            venv = Path(tmp) / "venv"
            venv.mkdir()
            (venv / "uv-receipt.toml").write_text(
                '[tool]\nrequirements = [{ name = "other-tool" }]\n', encoding="utf-8"
            )
            with (
                mock.patch.object(upgrade, "_is_editable_install", return_value=False),
                mock.patch.object(upgrade, "_looks_like_source", return_value=False),
            ):
                info = upgrade.detect(
                    exe=str(venv / "bin" / "python"),
                    prefix=str(venv),
                    base_prefix="/usr",
                    cwd=tmp,
                )
        self.assertEqual(info.method, upgrade.VENV)

    def test_uv_tool_venv_path_on_windows_keeps_the_drive(self):
        with mock.patch.object(
            upgrade.textfile, "read", return_value='requirements = [{ name = "lazyplan-tui" }]'
        ):
            prefix = "C:/Users/u/AppData/Local/uv/tools/lazyplan-tui"
            self.assertEqual(upgrade._looks_like_uv_tool(prefix), prefix)

    def test_uv_tool_dir_without_a_receipt_still_matches(self):
        with mock.patch.object(upgrade.textfile, "read", side_effect=OSError):
            prefix = "/home/u/.local/share/uv/tools/lazyplan-tui"
            self.assertEqual(upgrade._looks_like_uv_tool(prefix), prefix)

    def test_uv_tool_dir_outside_tools_is_not_uv(self):
        with mock.patch.object(upgrade.textfile, "read", side_effect=OSError):
            self.assertIsNone(upgrade._looks_like_uv_tool("/home/u/venvs/lazyplan-tui"))

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

    def test_package_manager_probes(self):
        cases = (("rpm", [True], upgrade.RPM), ("deb", [False, True], upgrade.DEB))
        for label, probes, method in cases:
            with self.subTest(case=label):
                with mock.patch.object(upgrade, "_probe", side_effect=probes):
                    info = upgrade.detect(exe="/usr/bin/python3", prefix="/usr", base_prefix="/usr")
                self.assertEqual(info.method, method)
                self.assertFalse(info.upgradeable)

    def test_source_checkout_layout(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "pyproject.toml").write_text(
                '[project]\nname = "lazyplan-tui"\n', encoding="utf-8"
            )
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
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        sandbox_home(self, self.tmp.name)

    def test_run_upgrade_routes_and_guards(self):
        cases = (
            ("unknown method", upgrade.InstallInfo(upgrade.RPM, False), "0.16.0", None),
            ("pipx", PIPX_INFO, "0.16.0", "pipx"),
            ("uv", UV_INFO, "0.16.0", "uv"),
            ("venv", VENV_INFO, "0.16.0", "venv"),
            ("downgrade", PIPX_INFO, "0.15.0", "reject"),
        )
        for label, info, version, outcome in cases:
            with self.subTest(case=label):
                with (
                    mock.patch.object(upgrade, "upgrade_pipx") as pipx_run,
                    mock.patch.object(upgrade, "upgrade_uv") as uv_run,
                    mock.patch.object(upgrade, "upgrade_venv") as venv_run,
                ):
                    if outcome == "reject":
                        with self.assertRaises(upgrade.UpgradeError):
                            upgrade.run_upgrade(info, version, installed="0.16.0")
                        pipx_run.assert_not_called()
                        uv_run.assert_not_called()
                        venv_run.assert_not_called()
                    elif outcome == "pipx":
                        upgrade.run_upgrade(info, version, installed="0.15.0")
                        pipx_run.assert_called_once_with(version, installed="0.15.0")
                        uv_run.assert_not_called()
                        venv_run.assert_not_called()
                    elif outcome == "uv":
                        upgrade.run_upgrade(info, version, installed="0.15.0")
                        uv_run.assert_called_once_with(version, installed="0.15.0")
                        pipx_run.assert_not_called()
                        venv_run.assert_not_called()
                    elif outcome == "venv":
                        upgrade.run_upgrade(
                            info, version, "/some/venv/bin/python", installed="0.15.0"
                        )
                        venv_run.assert_called_once_with(
                            version, "/some/venv/bin/python", installed="0.15.0"
                        )
                        pipx_run.assert_not_called()
                        uv_run.assert_not_called()

    def test_installed_upgraders_refuse_a_downgrade(self):
        with mock.patch.object(upgrade.subprocess, "run") as run:
            for label, action in (
                ("pipx", lambda: upgrade.upgrade_pipx("0.15.0", installed="0.16.0")),
                ("uv", lambda: upgrade.upgrade_uv("0.15.0", installed="0.16.0")),
                (
                    "venv",
                    lambda: upgrade.upgrade_venv("0.15.0", "/venv/bin/python", installed="0.16.0"),
                ),
            ):
                with self.subTest(case=label):
                    with self.assertRaises(upgrade.UpgradeError):
                        action()
        run.assert_not_called()

    def test_pipx_rejects_a_downgrade_without_a_subprocess(self):
        with mock.patch.object(upgrade.subprocess, "run") as run:
            with self.assertRaises(upgrade.UpgradeError):
                upgrade.upgrade_pipx("0.15.0", installed="0.16.0")
        run.assert_not_called()

    def test_venv_rejects_a_downgrade_without_a_subprocess(self):
        with mock.patch.object(upgrade.subprocess, "run") as run:
            with self.assertRaises(upgrade.UpgradeError):
                upgrade.upgrade_venv("0.15.0", "/venv/bin/python", installed="0.16.0")
        run.assert_not_called()

    def test_equal_version_is_refused(self):
        with self.assertRaises(upgrade.UpgradeError):
            upgrade.require_newer("0.16.0", installed="0.16.0")

    def test_pipx_upgrade_first_try_wins(self):
        ok = mock.Mock(returncode=0)
        with (
            mock.patch.object(upgrade.shutil, "which", return_value="/usr/bin/pipx"),
            mock.patch.object(upgrade.subprocess, "run", return_value=ok) as run,
        ):
            upgrade.upgrade_pipx("0.16.0", installed="0.15.0")
        self.assertEqual(run.call_count, 1)

    def test_pipx_upgrade_falls_back_to_force_install(self):
        bad = mock.Mock(returncode=1, stderr="", stdout="nope")
        good = mock.Mock(returncode=0)
        with (
            mock.patch.object(upgrade.shutil, "which", return_value="/usr/bin/pipx"),
            mock.patch.object(upgrade.subprocess, "run", side_effect=[bad, good]) as run,
        ):
            upgrade.upgrade_pipx("0.16.0", installed="0.15.0")
        self.assertEqual(run.call_count, 2)
        self.assertIn("--force", run.call_args[0][0])

    def test_pipx_upgrade_failure_raises(self):
        bad = mock.Mock(returncode=1, stderr="boom", stdout="")
        with (
            mock.patch.object(upgrade.shutil, "which", return_value="/usr/bin/pipx"),
            mock.patch.object(upgrade.subprocess, "run", return_value=bad),
        ):
            with self.assertRaises(upgrade.UpgradeError):
                upgrade.upgrade_pipx("0.16.0", installed="0.15.0")

    def test_pipx_failure_names_the_log(self):
        bad = mock.Mock(returncode=1, stderr="permission denied", stdout="")
        log_path = Path("/tmp/update-pipx.log")
        with (
            mock.patch.object(upgrade.shutil, "which", return_value="/usr/bin/pipx"),
            mock.patch.object(upgrade.subprocess, "run", return_value=bad),
            mock.patch.object(update_log, "record_update", return_value=log_path) as record,
        ):
            with self.assertRaises(upgrade.UpgradeError) as caught:
                upgrade.upgrade_pipx("0.16.0", installed="0.15.0")
        self.assertIn(str(log_path), str(caught.exception))
        record.assert_called()

    def test_pipx_missing_raises(self):
        with mock.patch.object(upgrade.shutil, "which", return_value=None):
            with self.assertRaises(upgrade.UpgradeError):
                upgrade.upgrade_pipx("0.16.0", installed="0.15.0")

    def test_uv_upgrade_first_try_wins(self):
        ok = mock.Mock(returncode=0)
        with (
            mock.patch.object(upgrade.shutil, "which", return_value="/usr/bin/uv"),
            mock.patch.object(upgrade.subprocess, "run", return_value=ok) as run,
        ):
            upgrade.upgrade_uv("0.16.0", installed="0.15.0")
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args[0][0], ["uv", "tool", "upgrade", "lazyplan-tui"])

    def test_uv_upgrade_falls_back_to_pinned_force_install(self):
        bad = mock.Mock(returncode=1, stderr="", stdout="nope")
        good = mock.Mock(returncode=0)
        with (
            mock.patch.object(upgrade.shutil, "which", return_value="/usr/bin/uv"),
            mock.patch.object(upgrade.subprocess, "run", side_effect=[bad, good]) as run,
        ):
            upgrade.upgrade_uv("0.16.0", installed="0.15.0")
        self.assertEqual(run.call_count, 2)
        fallback = run.call_args[0][0]
        self.assertEqual(fallback, ["uv", "tool", "install", "lazyplan-tui==0.16.0", "--force"])

    def test_uv_upgrade_failure_names_the_log(self):
        bad = mock.Mock(returncode=1, stderr="permission denied", stdout="")
        log_path = Path("/tmp/update-uv.log")
        with (
            mock.patch.object(upgrade.shutil, "which", return_value="/usr/bin/uv"),
            mock.patch.object(upgrade.subprocess, "run", return_value=bad),
            mock.patch.object(update_log, "record_update", return_value=log_path) as record,
        ):
            with self.assertRaises(upgrade.UpgradeError) as caught:
                upgrade.upgrade_uv("0.16.0", installed="0.15.0")
        self.assertIn(str(log_path), str(caught.exception))
        record.assert_called()

    def test_uv_missing_raises(self):
        with mock.patch.object(upgrade.shutil, "which", return_value=None):
            with self.assertRaises(upgrade.UpgradeError) as caught:
                upgrade.upgrade_uv("0.16.0", installed="0.15.0")
        self.assertIn("uv is not on PATH", str(caught.exception))

    def test_venv_reinstall_runs_venv_pip(self):
        ok = mock.Mock(returncode=0)
        with mock.patch.object(upgrade.subprocess, "run", return_value=ok) as run:
            upgrade.upgrade_venv(
                "0.16.0", "/home/u/.local/share/lazyplan-venv/bin/python", installed="0.15.0"
            )
        cmd = run.call_args[0][0]
        self.assertEqual(
            cmd,
            [
                "/home/u/.local/share/lazyplan-venv/bin/python",
                "-m",
                "pip",
                "install",
                "lazyplan-tui==0.16.0",
            ],
        )

    def test_venv_reinstall_failure_raises(self):
        bad = mock.Mock(returncode=1, stderr="boom", stdout="")
        with mock.patch.object(upgrade.subprocess, "run", return_value=bad):
            with self.assertRaises(upgrade.UpgradeError):
                upgrade.upgrade_venv(
                    "0.16.0", "/home/u/.local/share/lazyplan-venv/bin/python", installed="0.15.0"
                )


PIPX_INFO = upgrade.InstallInfo(upgrade.PIPX, True, "/home/u/.local/share/pipx/venvs/lazyplan-tui")
UV_INFO = upgrade.InstallInfo(upgrade.UV, True, "/home/u/.local/share/uv/tools/lazyplan-tui")
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
        with (
            mock.patch.object(upgrade.os, "name", "posix"),
            mock.patch.object(upgrade.shutil, "which", return_value=None),
        ):
            msg = upgrade.guard_message(upgrade.InstallInfo(upgrade.UNKNOWN, False))
        self.assertIn("install.sh", msg)

    def test_unknown_message_on_windows_points_at_pipx(self):
        with (
            mock.patch.object(upgrade.os, "name", "nt"),
            mock.patch.object(upgrade.shutil, "which", return_value=None),
        ):
            msg = upgrade.guard_message(upgrade.InstallInfo(upgrade.UNKNOWN, False))
        self.assertIn("pipx install --backend pip lazyplan-tui", msg)
        self.assertNotIn("install.sh", msg)

    def test_unknown_message_prefers_uv_when_present(self):
        with (
            mock.patch.object(upgrade.os, "name", "nt"),
            mock.patch.object(upgrade.shutil, "which", return_value="/usr/bin/uv"),
        ):
            msg = upgrade.guard_message(upgrade.InstallInfo(upgrade.UNKNOWN, False))
        self.assertIn("uv tool install lazyplan-tui", msg)

    def test_system_guards_list_every_upgradeable_method(self):
        for info in (
            upgrade.InstallInfo(upgrade.RPM, False),
            upgrade.InstallInfo(upgrade.DEB, False),
            upgrade.InstallInfo(upgrade.SOURCE, False, "editable"),
        ):
            with self.subTest(method=info.method):
                self.assertIn("pipx, uv, and venv", upgrade.guard_message(info))


class TestHints(unittest.TestCase):
    def test_reinstall_hint_prefers_uv_when_present(self):
        with mock.patch.object(upgrade.shutil, "which", return_value="/usr/bin/uv"):
            self.assertEqual(upgrade.reinstall_hint(), "uv tool install lazyplan-tui")

    def test_reinstall_hint_falls_back_to_pipx_on_windows(self):
        with (
            mock.patch.object(upgrade.shutil, "which", return_value=None),
            mock.patch.object(upgrade.os, "name", "nt"),
        ):
            self.assertIn("pipx install", upgrade.reinstall_hint())

    def test_reinstall_hint_falls_back_to_installer_on_posix(self):
        with (
            mock.patch.object(upgrade.shutil, "which", return_value=None),
            mock.patch.object(upgrade.os, "name", "posix"),
        ):
            self.assertIn("install.sh", upgrade.reinstall_hint())

    def test_uv_diagnostics_name_the_tool_venv_and_repair(self):
        with (
            mock.patch.object(upgrade.shutil, "which", return_value="/usr/bin/uv"),
            mock.patch.object(upgrade, "detect", return_value=UV_INFO),
        ):
            data = upgrade.diagnostics()
        self.assertEqual(data["method"], upgrade.UV)
        self.assertEqual(data["uv_tool"], UV_INFO.detail)
        self.assertIn("uv tool install", str(data["repair"]))

    def test_notice_for_uv_says_run_upgrade(self):
        notice = upgrade.notice_text(UV_INFO, "0.15.0", "0.16.0") or ""
        self.assertIn("lpui upgrade", notice)


class TestUpgradeCommand(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(cli_mod, "_is_windows", return_value=False)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        sandbox_home(self, self.tmp.name)

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

    def test_check_reports_uv_method(self):
        with (
            mock.patch.object(cli_mod, "detect", return_value=UV_INFO),
            mock.patch.object(cli_mod, "latest_version", return_value="9.9.9"),
            mock.patch.object(cli_mod, "run_upgrade") as run,
        ):
            code, out, _ = self._run(["upgrade", "--check"])
        self.assertEqual(code, 0)
        self.assertIn("uv", out)
        run.assert_not_called()

    def test_uv_diagnose_json_names_the_tool_venv(self):
        with (
            mock.patch.object(upgrade.shutil, "which", return_value="/usr/bin/uv"),
            mock.patch.object(upgrade, "detect", return_value=UV_INFO),
        ):
            code, out, _ = self._run(["upgrade", "--diagnose", "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["method"], upgrade.UV)
        self.assertEqual(payload["uv_tool"], UV_INFO.detail)

    def test_diagnose_json_reports_the_environment_without_network(self):
        payload = {
            "method": upgrade.PIPX,
            "exe": "C:/venv/Scripts/python.exe",
            "pipx": "C:/pipx/bin/pipx.exe",
            "log_dir": "C:/Users/u/AppData/Local/lazyplan/logs",
        }
        with (
            mock.patch.object(cli_mod, "diagnostics", return_value=payload) as diag,
            mock.patch.object(cli_mod, "latest_version") as latest,
        ):
            code, out, _ = self._run(["upgrade", "--diagnose", "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out), payload)
        diag.assert_called_once()
        latest.assert_not_called()

    def test_diagnose_human_output_names_paths(self):
        payload = {
            "method": upgrade.PIPX,
            "exe": "C:/venv/Scripts/python.exe",
            "log_dir": "C:/Users/u/AppData/Local/lazyplan/logs",
        }
        with mock.patch.object(cli_mod, "diagnostics", return_value=payload):
            code, out, _ = self._run(["upgrade", "--diagnose"])
        self.assertEqual(code, 0)
        self.assertIn("pipx", out)
        self.assertIn("C:/venv/Scripts/python.exe", out)
        self.assertIn("log_dir", out)

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
            mock.patch.object(cli_mod.subprocess, "run") as spawn,
        ):
            code, _out, _ = self._run(["upgrade"])
        self.assertEqual(code, 0)
        spawn.assert_called_once()
        argv = spawn.call_args.args[0]
        self.assertEqual(argv[0], sys.executable)
        self.assertEqual(argv[1:3], ["-m", "lazyplan"])
        self.assertEqual(argv[3:], ["setup", "--post-upgrade"])

    def test_json_upgrade_still_refreshes_setup(self):
        with (
            mock.patch.object(cli_mod, "detect", return_value=PIPX_INFO),
            mock.patch.object(cli_mod, "latest_version", return_value="9.9.9"),
            mock.patch.object(cli_mod, "run_upgrade"),
            mock.patch.object(cli_mod.subprocess, "run") as spawn,
        ):
            code, out, _ = self._run(["upgrade", "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertTrue(payload["upgraded"])
        spawn.assert_called_once()
        self.assertEqual(spawn.call_args.args[0][3:], ["setup", "--post-upgrade", "--json"])

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

    def test_windows_upgrade_stages_and_spawns_the_helper(self):
        staged = mock.Mock()
        plan = mock.Mock()
        log = Path("/logs/update-apply.log")
        with (
            mock.patch.object(cli_mod, "detect", return_value=PIPX_INFO),
            mock.patch.object(cli_mod, "latest_version", return_value="9.9.9"),
            mock.patch.object(cli_mod, "_is_windows", return_value=True),
            mock.patch.object(cli_mod, "stage_update", return_value=staged) as stage,
            mock.patch.object(cli_mod, "build_apply_plan", return_value=plan) as build,
            mock.patch.object(cli_mod, "spawn_windows_apply", return_value=log) as spawn,
            mock.patch.object(cli_mod, "run_upgrade") as run,
        ):
            code, out, _ = self._run(["upgrade", "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertTrue(payload["started"])
        self.assertFalse(payload["restart"])
        self.assertEqual(payload["log"], str(log))
        stage.assert_called_once()
        build.assert_called_once_with(staged, exe=sys.executable, windows=True, restart=False)
        spawn.assert_called_once_with(plan, parent_pid=os.getpid())
        run.assert_not_called()

    def test_windows_stage_failure_is_reported(self):
        with (
            mock.patch.object(cli_mod, "detect", return_value=PIPX_INFO),
            mock.patch.object(cli_mod, "latest_version", return_value="9.9.9"),
            mock.patch.object(cli_mod, "_is_windows", return_value=True),
            mock.patch.object(
                cli_mod,
                "stage_update",
                side_effect=update_stage.StageError("no verified wheel"),
            ),
        ):
            code, _out, err = self._run(["upgrade"])
        self.assertEqual(code, 1)
        self.assertIn("no verified wheel", err)

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
