"""Windows ApplyPlan, detached spawn, parent wait, and stale-state recovery."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from lazyplan import _update_helper
from lazyplan.infrastructure import update_apply, update_stage
from lazyplan.infrastructure.update_apply import ApplyPlan, build_apply_plan
from lazyplan.infrastructure.upgrade import PIPX, VENV, InstallInfo

URL = "https://files.pythonhosted.org/packages/x/w.whl"


def staged(method: str = PIPX) -> update_stage.StagedUpdate:
    return update_stage.StagedUpdate(
        "9.9.9",
        method,
        "lazyplan_tui-9.9.9-py3-none-any.whl",
        URL,
        "a" * 64,
        10,
        1000.0,
    )


class TestApplyPlan(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name) / "home"
        self.home.mkdir()

    def test_pipx_windows_plan_keeps_backend_and_uses_the_venv_python(self) -> None:
        update = staged(PIPX)
        info = InstallInfo(PIPX, True, "C:/Users/u/pipx/venvs/lazyplan-tui")
        with mock.patch.object(
            update_apply.shutil,
            "which",
            side_effect=["C:/Users/u/pipx/bin/pipx.exe", "C:/Users/u/pipx/bin/lpui.exe"],
        ):
            plan = build_apply_plan(
                update,
                home=self.home,
                exe="C:/Users/u/pipx/venvs/lazyplan-tui/Scripts/python.exe",
                info=info,
                windows=True,
                argv=("ui",),
            )
        wheel = str(update_stage.wheel_path(update, self.home))
        python = str(Path("C:/Users/u/pipx/venvs/lazyplan-tui/Scripts/python.exe"))
        self.assertEqual(Path(plan.python), Path(python))
        self.assertEqual(plan.command, (python, "-m", "pip", "install", "--no-input", wheel))
        self.assertEqual(Path(plan.scripts), Path("C:/Users/u/pipx/bin"))
        self.assertEqual(Path(plan.restart[0]), Path("C:/Users/u/pipx/bin/lpui.exe"))
        self.assertEqual(plan.restart[1:], ("ui",))
        self.assertEqual(plan.log_path.parent, update_apply.update_log.logs_dir(self.home))

    def test_venv_windows_plan_uses_the_owning_pip(self) -> None:
        update = staged(VENV)
        info = InstallInfo(VENV, True, "C:/Users/u/lazyplan-venv")
        plan = build_apply_plan(
            update,
            home=self.home,
            exe="C:/Users/u/lazyplan-venv/Scripts/python.exe",
            info=info,
            windows=True,
        )
        wheel = str(update_stage.wheel_path(update, self.home))
        self.assertEqual(
            plan.command,
            (
                "C:/Users/u/lazyplan-venv/Scripts/python.exe",
                "-m",
                "pip",
                "install",
                "--no-input",
                wheel,
            ),
        )
        self.assertEqual(
            plan.restart,
            ("C:/Users/u/lazyplan-venv/Scripts/python.exe", "-m", "lazyplan"),
        )

    def test_posix_pipx_command_stays_synchronous(self) -> None:
        update = staged(PIPX)
        info = InstallInfo(PIPX, True, "/home/u/.local/share/pipx/venvs/lazyplan-tui")
        with mock.patch.object(update_apply.shutil, "which", return_value="/usr/bin/pipx"):
            plan = build_apply_plan(
                update,
                home=self.home,
                exe="/home/u/.local/share/pipx/venvs/lazyplan-tui/bin/python",
                info=info,
                windows=False,
            )
        wheel = str(update_stage.wheel_path(update, self.home))
        self.assertNotIn("--backend", plan.command)
        self.assertEqual(plan.command[-2:], (wheel, "--force"))

    def test_log_path_is_unique_and_under_the_logs_dir(self) -> None:
        plan = build_apply_plan(
            staged(VENV),
            home=self.home,
            exe="/venv/bin/python",
            info=InstallInfo(VENV, True, "/venv"),
            windows=True,
            now=1000.0,
            pid=42,
        )
        self.assertEqual(plan.log_path.name, "update-apply-1000-42.log")
        self.assertNotEqual(
            plan.log_path,
            build_apply_plan(
                staged(VENV),
                home=self.home,
                exe="/venv/bin/python",
                info=InstallInfo(VENV, True, "/venv"),
                windows=True,
                now=1000.0,
                pid=43,
            ).log_path,
        )

    def test_helper_command_carries_the_plan_and_parent(self) -> None:
        plan = build_apply_plan(
            staged(VENV),
            home=self.home,
            exe="/venv/bin/python",
            info=InstallInfo(VENV, True, "/venv"),
            windows=True,
            now=1000.0,
            pid=42,
        )
        command = update_apply.helper_command(plan, parent_pid=123)
        self.assertEqual(command[:3], [plan.python, "-m", "lazyplan._update_helper"])
        self.assertEqual(command[command.index("--parent-pid") + 1], "123")
        payload = json.loads(command[command.index("--plan-json") + 1])
        self.assertEqual(payload["wheel"], str(plan.wheel))
        self.assertEqual(payload["log"], str(plan.log_path))


class TestSpawnAndWait(unittest.TestCase):
    def test_spawn_uses_detached_flags_and_returns_the_log(self) -> None:
        plan = ApplyPlan(
            wheel=Path("/wheel.whl"),
            method=VENV,
            python="/venv/bin/python",
            pipx="",
            command=("/venv/bin/python", "-m", "pip", "install", "/wheel.whl"),
            restart=("/venv/bin/python", "-m", "lazyplan"),
            scripts=Path("/venv/bin"),
            log_path=Path("/home/.lazyplan/logs/update-apply-1-2.log"),
            home=Path("/home"),
            windows=True,
        )
        with mock.patch.object(update_apply.subprocess, "Popen") as popen:
            path = update_apply.spawn_windows_apply(plan, parent_pid=123)
        self.assertEqual(path, plan.log_path)
        kwargs = popen.call_args.kwargs
        self.assertTrue(kwargs["close_fds"])
        self.assertEqual(kwargs["stdin"], update_apply.subprocess.DEVNULL)
        self.assertNotEqual(kwargs["creationflags"], 0)

    def test_wait_for_parent_succeeds_and_times_out(self) -> None:
        values = iter([True, True, False])
        self.assertTrue(
            update_apply.wait_for_parent(
                10,
                timeout=1.0,
                poll=0.0,
                alive=lambda _pid: next(values),
            )
        )
        self.assertFalse(
            update_apply.wait_for_parent(
                10,
                timeout=0.0,
                poll=0.0,
                alive=lambda _pid: True,
            )
        )


class TestHelperRun(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.plan = ApplyPlan(
            wheel=Path("/wheel.whl"),
            method=VENV,
            python="/venv/bin/python",
            pipx="",
            command=("/venv/bin/python", "-m", "pip", "install", "/wheel.whl"),
            restart=("/venv/bin/python", "-m", "lazyplan"),
            scripts=Path("/venv/bin"),
            log_path=self.root / "logs" / "update-apply.log",
            home=self.root,
            windows=True,
        )

    def test_success_logs_clears_and_restarts(self) -> None:
        install = mock.Mock(returncode=0, stdout="installed", stderr="")
        setup = mock.Mock(returncode=0, stdout="setup ok", stderr="")
        with (
            mock.patch.object(_update_helper, "wait_for_parent", return_value=True),
            mock.patch.object(
                _update_helper.subprocess,
                "run",
                side_effect=[install, setup],
            ),
            mock.patch.object(update_stage, "clear_apply") as clear,
            mock.patch.object(_update_helper, "_restart") as restart,
        ):
            code = _update_helper.run(self.plan, 42)
        self.assertEqual(code, 0)
        clear.assert_called_once_with(self.root, self.plan.wheel)
        restart.assert_called_once_with(self.plan)
        text = self.plan.log_path.read_text(encoding="utf-8")
        self.assertIn("installed", text)
        self.assertIn("setup_returncode: 0", text)

    def test_install_failure_parks_without_restart(self) -> None:
        install = mock.Mock(returncode=1, stdout="", stderr="permission denied")
        with (
            mock.patch.object(_update_helper, "wait_for_parent", return_value=True),
            mock.patch.object(_update_helper.subprocess, "run", return_value=install),
            mock.patch.object(update_stage, "park_failure") as park,
            mock.patch.object(_update_helper, "_restart") as restart,
        ):
            code = _update_helper.run(self.plan, 42)
        self.assertEqual(code, 1)
        park.assert_called_once()
        self.assertIn("permission denied", park.call_args.args[0])
        restart.assert_not_called()

    def test_parent_timeout_parks(self) -> None:
        with (
            mock.patch.object(_update_helper, "wait_for_parent", return_value=False),
            mock.patch.object(update_stage, "park_failure") as park,
        ):
            code = _update_helper.run(self.plan, 42)
        self.assertEqual(code, 2)
        self.assertIn("timed out", park.call_args.args[0])


class TestStaleApply(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name) / "home"
        self.home.mkdir()

    def test_stale_applying_is_parked_with_a_failure(self) -> None:
        applying = update_stage._state_path(update_stage.APPLYING, self.home)
        applying.parent.mkdir(parents=True)
        applying.write_text("{}\n", encoding="utf-8")
        old = 1000.0
        os.utime(applying, (old, old))
        error = update_stage.recover_stale_apply(
            self.home,
            now=old + update_stage.STALE_APPLY + 1,
            stale_after=update_stage.STALE_APPLY,
        )
        self.assertIn("did not finish", error or "")
        self.assertFalse(applying.exists())


if __name__ == "__main__":
    unittest.main()
