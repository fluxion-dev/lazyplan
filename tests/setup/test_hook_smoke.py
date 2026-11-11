"""Smoke the installed hook command, not the service function directly."""

import json
import os
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from lazyplan import services
from lazyplan.core.entities import Status
from lazyplan.infrastructure import hook_install
from lazyplan.store import Store
from tests.support.home import sandbox_home


class SmokeCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        self.home.mkdir()
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q", self.repo], check=True)
        sandbox_home(self, str(self.home))
        for key in ("LAZYPLAN_DB", "LAZYPLAN_HOOKS", "LAZYPLAN_NO_HOOKS"):
            self.addCleanup(self._restore, key, os.environ.pop(key, None))

    def tearDown(self):
        self.tmp.cleanup()

    @staticmethod
    def _restore(key: str, value: str | None) -> None:
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value

    def _store(self) -> Store:
        return Store(self.repo / ".agents/lazyplan/lazyplan.db")

    def _linked_plan(self, doing: bool = False) -> None:
        store = self._store()
        plan = store.add_plan("P", "what", goal="why")
        milestone = store.add_milestone(plan.id, "M", "desc")
        task = store.add_task(milestone.id, "Task", "desc")
        if doing:
            services.set_status(store, "task", task.id, Status.DOING, actor="t")
            services.set_status(store, "milestone", milestone.id, Status.DOING, actor="t")
            services.set_status(store, "plan", plan.id, Status.DOING, actor="t")

    def _command(self, mode: str) -> list[str]:
        hook_install.install(self.home, ["claude"], mode=mode)
        settings = json.loads((self.home / ".claude/settings.json").read_text(encoding="utf-8"))
        command = settings["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
        argv = shlex.split(command)
        if argv and argv[0] == "lpui":
            return [sys.executable, "-m", "lazyplan", *argv[1:]]
        return argv

    def _run(self, argv: list[str]) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2] / "src")
        return subprocess.run(
            argv,
            input=json.dumps({"tool_input": {"command": "git commit -m x"}}),
            text=True,
            capture_output=True,
            cwd=self.repo,
            env=env,
            timeout=30,
        )

    def test_strict_installed_command_denies_a_commit(self):
        self._linked_plan(doing=False)
        result = self._run(self._command("strict"))
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_advisory_installed_command_only_reminds(self):
        self._linked_plan(doing=False)
        result = self._run(self._command("advisory"))
        self.assertEqual(result.returncode, 0, result.stderr)
        body = json.loads(result.stdout)
        self.assertNotIn("permissionDecision", body.get("hookSpecificOutput", {}))

    def test_installed_command_allows_a_doing_task(self):
        self._linked_plan(doing=True)
        result = self._run(self._command("strict"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "")


if __name__ == "__main__":
    unittest.main()
