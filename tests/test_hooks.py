"""Canonical hook protocol: events, read-only behavior, and plain output."""

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from lazyplan import audit, hooks, services
from lazyplan.cli import main as lpui_main
from lazyplan.models import Status
from lazyplan.store import Store
from tests.support.home import sandbox_home


class HookCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        self.home.mkdir()
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir()
        self.old_db = os.environ.pop("LAZYPLAN_DB", None)
        self.old_nohooks = os.environ.pop(hooks.NO_HOOKS_ENV, None)
        self.old_cwd = os.getcwd()
        sandbox_home(self, str(self.home))
        os.chdir(self.repo)
        self.db = self.home / ".lazyplan/lazyplan.db"

    def tearDown(self):
        os.chdir(self.old_cwd)
        for key, value in (
            ("LAZYPLAN_DB", self.old_db),
            (hooks.NO_HOOKS_ENV, self.old_nohooks),
        ):
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()

    def _seed(self) -> tuple[int, int]:
        store = Store(self.db)
        plan = store.add_plan("P", "what", goal="why")
        milestone = store.add_milestone(plan.id, "M", "desc")
        task = store.add_task(milestone.id, "Doing task", "desc")
        services.set_status(store, "task", task.id, Status.DOING, actor="t")
        services.set_status(store, "milestone", milestone.id, Status.DOING, actor="t")
        services.set_status(store, "plan", plan.id, Status.DOING, actor="t")
        return plan.id, task.id

    def test_read_payload_tolerates_garbage(self):
        self.assertEqual(hooks.read_payload(io.StringIO("")), {})
        self.assertEqual(hooks.read_payload(io.StringIO("{nope")), {})
        self.assertEqual(hooks.read_payload(io.StringIO("[1]")), {})

    def test_detect_host_from_payload_and_explicit(self):
        self.assertEqual(hooks.detect_host({}, "codex"), "codex")
        self.assertEqual(hooks.detect_host({"hook_event_name": "SessionStart"}), "claude")
        self.assertEqual(hooks.detect_host({"workspace_roots": []}), "cursor")

    def test_session_start_names_the_doing_task(self):
        _plan, _task = self._seed()
        result = hooks.build_result("session-start", {}, self.repo, commits=[])
        self.assertIn("Doing task", result.text)
        self.assertTrue(result.context)

    def test_missing_database_is_silent(self):
        self.assertEqual(
            hooks.build_result("session-start", {}, self.repo, commits=[]), hooks.HookResult()
        )

    def test_post_tool_commit_asks_for_a_link(self):
        _plan, task_id = self._seed()
        payload = {"tool_input": {"command": "git commit -m x"}}
        result = hooks.build_result("post-tool", payload, self.repo, commits=[])
        self.assertIn(f"--id {task_id}", result.text)

    def test_post_tool_other_commands_are_silent(self):
        self._seed()
        payload = {"tool_input": {"command": "git status"}}
        self.assertEqual(hooks.build_result("post-tool", payload, self.repo, commits=[]).text, "")

    def test_opt_out_is_silent(self):
        self._seed()
        os.environ[hooks.NO_HOOKS_ENV] = "1"
        self.assertEqual(hooks.run("session-start", {}, commits=[]).text, "")

    def test_hook_is_read_only(self):
        self._seed()
        before = self.db.read_bytes()
        hooks.build_result("session-start", {}, self.repo, commits=[])
        self.assertEqual(self.db.read_bytes(), before)

    def test_cli_json_and_fresh_home(self):
        self._seed()
        out = io.StringIO()
        old_stdin = sys.stdin
        sys.stdin = io.StringIO(json.dumps({"tool_input": {"command": "git commit"}}))
        try:
            with redirect_stdout(out):
                code = lpui_main(["hook", "session-start", "--json", "--host", "claude"])
        finally:
            sys.stdin = old_stdin
        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["host"], "claude")
        self.assertIn("Doing task", payload["text"])

    def test_stop_warns_about_unlinked_commits(self):
        self._seed()
        commits = [audit.Commit("a" * 40, 1000, self.repo.as_posix(), 1, "loose")]
        result = hooks.build_result("stop", {}, self.repo, commits=commits)
        self.assertIn("unlinked", result.text)

    def test_closed_plan_is_silent(self):
        store = Store(self.db)
        plan = store.add_plan("P", "what", goal="why")
        milestone = store.add_milestone(plan.id, "M", "desc")
        task = store.add_task(milestone.id, "T", "desc")
        for kind, obj_id in (("task", task.id), ("milestone", milestone.id), ("plan", plan.id)):
            services.set_status(store, kind, obj_id, Status.DONE, actor="t")
        result = hooks.build_result("session-start", {}, self.repo, commits=[])
        self.assertEqual(result.text, "")

    def test_cli_fresh_home_creates_nothing(self):
        out = io.StringIO()
        old_stdin = sys.stdin
        sys.stdin = io.StringIO("")
        try:
            with redirect_stdout(out):
                code = lpui_main(["hook", "session-start"])
        finally:
            sys.stdin = old_stdin
        self.assertEqual(code, 0)
        self.assertFalse((self.home / ".lazyplan").exists())


if __name__ == "__main__":
    unittest.main()
