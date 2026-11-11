"""Canonical hook protocol: events, read-only behavior, and plain output."""

import io
import json
import os
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from lazyplan import services
from lazyplan.core.entities import Status
from lazyplan.presentation.cli import main as lpui_main
from lazyplan.services import audit, hooks
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
        store.add_task(milestone.id, "Next task", "desc")
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
        result = hooks.build_result(
            "session-start", {}, self.repo, commits=[], store=Store(self.db)
        )
        self.assertIn("Doing task", result.text)
        self.assertIn("next", result.text)
        self.assertTrue(result.context)

    def test_pre_compact_injects_the_context_packet(self):
        _plan, _task = self._seed()
        result = hooks.build_result("pre-compact", {}, self.repo, commits=[], store=Store(self.db))
        self.assertIn("Doing task", result.text)
        self.assertTrue(result.context)

    def test_session_handoff_is_in_session_start(self):
        plan_id, _task = self._seed()
        store = Store(self.db)
        session, _ = store.start_session("ana", plan_id=plan_id, now=100.0)
        store.end_session(session.id, "ana", summary="shipped", handoff="next: QA", now=200.0)
        result = hooks.build_result(
            "session-start", {}, self.repo, commits=[], store=Store(self.db)
        )
        self.assertIn("next: QA", result.text)

    def test_open_session_is_marked_awaiting_on_stop(self):
        _plan, _task = self._seed()
        store = Store(self.db)
        session, _ = store.start_session("ana", now=time.time())
        result = hooks.build_result("stop", {}, self.repo, commits=[], store=Store(self.db))
        self.assertIn(f"S{session.id} is awaiting", result.text)
        updated = Store(self.db).get_session(session.id)
        assert updated is not None
        self.assertTrue(updated.awaiting)
        self.assertGreater(updated.last_seen_at, 0)

    def _unlinked(self):
        plan_id, task_id = self._seed()
        Store(self.db).add_repo_link("plan", plan_id, str(self.repo), actor="t")
        commit = audit.Commit(
            sha="a" * 40,
            timestamp=int(time.time()),
            subject="work",
            repo=str(self.repo),
        )
        return task_id, [commit]

    def test_prompt_submit_injects_the_active_plan(self):
        _plan, task_id = self._seed()
        result = hooks.build_result(
            "prompt-submit", {}, self.repo, commits=[], store=Store(self.db)
        )
        self.assertTrue(result.context)
        self.assertIn(f"T{task_id}", result.text)
        self.assertIn("next", result.text)
        self.assertLessEqual(len(result.text), 1200)

    def test_prompt_submit_is_silent_without_plans(self):
        result = hooks.build_result(
            "prompt-submit", {}, self.repo, commits=[], store=Store(self.db)
        )
        self.assertEqual(result.text, "")

    def test_stop_blocks_once_for_unlinked_commits(self):
        _task_id, commits = self._unlinked()
        result = hooks.build_result(
            "stop",
            {},
            self.repo,
            commits=commits,
            store=Store(self.db),
            mode="strict",
            host="claude",
        )
        self.assertIn("unlinked commits", result.block)
        self.assertIn("lpui link --kind task", result.block)

    def test_continued_stop_is_allowed(self):
        _task_id, commits = self._unlinked()
        result = hooks.build_result(
            "stop",
            {"stop_hook_active": True},
            self.repo,
            commits=commits,
            store=Store(self.db),
            mode="strict",
            host="claude",
        )
        self.assertEqual(result.block, "")

    def test_cursor_loop_count_allows_the_second_stop(self):
        _task_id, commits = self._unlinked()
        result = hooks.build_result(
            "stop",
            {"loop_count": 1},
            self.repo,
            commits=commits,
            store=Store(self.db),
            mode="strict",
            host="cursor",
        )
        self.assertEqual(result.block, "")

    def test_advisory_stop_reminds_without_blocking(self):
        _task_id, commits = self._unlinked()
        result = hooks.build_result(
            "stop",
            {},
            self.repo,
            commits=commits,
            store=Store(self.db),
            mode="advisory",
            host="claude",
        )
        self.assertEqual(result.block, "")
        self.assertIn("unlinked", result.text)

    def test_opencode_never_blocks_a_stop(self):
        _task_id, commits = self._unlinked()
        result = hooks.build_result(
            "stop",
            {},
            self.repo,
            commits=commits,
            store=Store(self.db),
            mode="strict",
            host="opencode",
        )
        self.assertEqual(result.block, "")

    def test_unmanaged_repo_does_not_block_a_stop(self):
        _plan, _task = self._seed()
        commit = audit.Commit(sha="a" * 40, timestamp=int(time.time()), subject="work")
        result = hooks.build_result(
            "stop",
            {},
            self.repo,
            commits=[commit],
            store=Store(self.db),
            mode="strict",
            host="claude",
        )
        self.assertEqual(result.block, "")

    def test_session_end_closes_with_a_summary_and_handoff(self):
        _plan, task_id = self._seed()
        store = Store(self.db)
        session, _ = store.start_session("ana", repo_path=str(self.repo), now=time.time())
        hooks.build_result(
            "session-end",
            {},
            self.repo,
            commits=[],
            store=Store(self.db),
            host="claude",
        )
        closed = Store(self.db).get_session(session.id)
        assert closed is not None
        self.assertTrue(closed.ended)
        self.assertIn("ended by claude", closed.summary)
        self.assertIn(f"T{task_id}", closed.summary)
        self.assertIn("next: T", closed.handoff)

    def test_session_end_without_a_session_creates_nothing(self):
        self._seed()
        hooks.build_result(
            "session-end", {}, self.repo, commits=[], store=Store(self.db), host="claude"
        )
        self.assertEqual(Store(self.db).list_sessions(open_only=True), [])

    def test_missing_database_is_silent(self):
        self.assertEqual(
            hooks.build_result("session-start", {}, self.repo, commits=[], store=None),
            hooks.HookResult(),
        )

    def test_post_tool_commit_asks_for_a_link(self):
        _plan, task_id = self._seed()
        payload = {"tool_input": {"command": "git commit -m x"}}
        result = hooks.build_result(
            "post-tool", payload, self.repo, commits=[], store=Store(self.db)
        )
        self.assertIn(f"--id {task_id}", result.text)

    def _linked_plan(self) -> int:
        store = Store(self.db)
        plan = store.add_plan("Linked", "what", goal="why")
        store.add_repo_link("plan", plan.id, str(self.repo), actor="t")
        return plan.id

    def test_commit_is_blocked_without_a_doing_task(self):
        self._linked_plan()
        payload = {"tool_input": {"command": "git commit -m x"}}
        result = hooks.build_result(
            "pre-tool", payload, self.repo, commits=[], store=Store(self.db), mode="strict"
        )
        self.assertIn("no doing task", result.block)
        self.assertIn("lpui next", result.block)

    def test_commit_is_allowed_with_a_doing_task(self):
        plan_id, _task = self._seed()
        Store(self.db).add_repo_link("plan", plan_id, str(self.repo), actor="t")
        payload = {"tool_input": {"command": "git commit -m x"}}
        result = hooks.build_result(
            "pre-tool", payload, self.repo, commits=[], store=Store(self.db), mode="strict"
        )
        self.assertEqual(result.block, "")

    def test_advisory_commit_reminds_without_blocking(self):
        self._linked_plan()
        payload = {"tool_input": {"command": "git commit -m x"}}
        result = hooks.build_result(
            "pre-tool", payload, self.repo, commits=[], store=Store(self.db), mode="advisory"
        )
        self.assertEqual(result.block, "")
        self.assertIn("no doing task", result.text)

    def test_commit_in_an_unmanaged_checkout_is_allowed(self):
        self._seed()
        payload = {"tool_input": {"command": "git commit -m x"}}
        result = hooks.build_result(
            "pre-tool", payload, self.repo, commits=[], store=Store(self.db), mode="strict"
        )
        self.assertEqual(result.block, "")

    def test_non_git_commands_are_never_blocked(self):
        self._linked_plan()
        payload = {"tool_input": {"command": "git status"}}
        result = hooks.build_result(
            "pre-tool", payload, self.repo, commits=[], store=Store(self.db), mode="strict"
        )
        self.assertEqual(result.block, "")

    def test_post_tool_edit_names_the_owning_task(self):
        _plan, task_id = self._seed()
        Store(self.db).add_touchpoint(task_id, "src/**", actor="t")
        payload = {"tool_name": "Edit", "tool_input": {"file_path": "src/app.py"}}
        result = hooks.build_result(
            "post-tool", payload, self.repo, commits=[], store=Store(self.db)
        )
        self.assertIn(f"T{task_id}", result.text)

    def test_post_tool_edit_outside_the_task_asks_for_scope(self):
        _plan, _task = self._seed()
        payload = {"tool_name": "Write", "tool_input": {"file_path": "docs/readme.md"}}
        result = hooks.build_result(
            "post-tool", payload, self.repo, commits=[], store=Store(self.db)
        )
        self.assertIn("scope", result.text)

    def test_post_tool_apply_patch_reads_the_patch_path(self):
        _plan, task_id = self._seed()
        Store(self.db).add_touchpoint(task_id, "src/**", actor="t")
        payload = {
            "tool_name": "apply_patch",
            "tool_input": {"command": "*** Begin Patch\n*** Update File: src/x.py\n"},
        }
        result = hooks.build_result(
            "post-tool", payload, self.repo, commits=[], store=Store(self.db)
        )
        self.assertIn(f"T{task_id}", result.text)

    def test_post_tool_edit_without_a_task_points_at_brief(self):
        payload = {"tool_name": "Edit", "tool_input": {"file_path": "src/app.py"}}
        result = hooks.build_result(
            "post-tool", payload, self.repo, commits=[], store=Store(self.db)
        )
        self.assertIn("lpui brief", result.text)

    def test_post_tool_other_commands_are_silent(self):
        self._seed()
        payload = {"tool_input": {"command": "git status"}}
        self.assertEqual(
            hooks.build_result(
                "post-tool", payload, self.repo, commits=[], store=Store(self.db)
            ).text,
            "",
        )

    def test_opt_out_is_silent(self):
        self._seed()
        os.environ[hooks.NO_HOOKS_ENV] = "1"
        self.assertEqual(hooks.run("session-start", {}, commits=[]).text, "")

    def test_session_start_tracks_a_session(self):
        self._seed()
        hooks.build_result("session-start", {}, self.repo, commits=[], store=Store(self.db))
        sessions = Store(self.db).list_sessions(open_only=True)
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0].phase, "working")
        self.assertTrue(sessions[0].host)

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
        result = hooks.build_result("stop", {}, self.repo, commits=commits, store=Store(self.db))
        self.assertIn("unlinked", result.text)

    def test_closed_plan_is_silent(self):
        store = Store(self.db)
        plan = store.add_plan("P", "what", goal="why")
        milestone = store.add_milestone(plan.id, "M", "desc")
        task = store.add_task(milestone.id, "T", "desc")
        for kind, obj_id in (("task", task.id), ("milestone", milestone.id), ("plan", plan.id)):
            services.set_status(store, kind, obj_id, Status.DONE, actor="t")
        result = hooks.build_result(
            "session-start", {}, self.repo, commits=[], store=Store(self.db)
        )
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
