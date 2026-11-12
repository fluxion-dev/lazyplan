"""Canonical hook protocol: events, read-only behavior, and plain output."""

import io
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from lazyplan import services
from lazyplan.core.entities import Status
from lazyplan.infrastructure.repo import git_common_dir
from lazyplan.presentation.cli import main as lpui_main
from lazyplan.presentation.cli.parser import build_parser
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

    def _seed_linked(self) -> tuple[int, int]:
        plan_id, task_id = self._seed()
        Store(self.db).add_repo_link("plan", plan_id, str(self.repo), actor="t")
        return plan_id, task_id

    def _git(self, *args: str) -> None:
        subprocess.run(["git", *args], cwd=self.repo, check=True, capture_output=True)

    def _init_git(self, branch: str) -> None:
        self._git("init", "-b", branch)
        self._git("config", "user.email", "test@example.com")
        self._git("config", "user.name", "Test")
        (self.repo / "file.txt").write_text("one\n", encoding="utf-8")
        self._git("add", "file.txt")
        self._git("commit", "-m", "init")

    def test_read_payload_tolerates_garbage(self):
        self.assertEqual(hooks.read_payload(io.StringIO("")), {})
        self.assertEqual(hooks.read_payload(io.StringIO("{nope")), {})
        self.assertEqual(hooks.read_payload(io.StringIO("[1]")), {})

    def test_read_payload_does_not_wait_for_an_open_pipe(self):
        read_fd, write_fd = os.pipe()
        reader = os.fdopen(read_fd, "r", encoding="utf-8")
        try:
            started = time.monotonic()
            self.assertEqual(hooks.read_payload(reader), {})
            self.assertLess(time.monotonic() - started, 1.0)
        finally:
            reader.close()
            os.close(write_fd)

    def test_read_payload_keeps_a_payload_on_an_open_pipe(self):
        read_fd, write_fd = os.pipe()
        reader = os.fdopen(read_fd, "r", encoding="utf-8")
        try:
            os.write(write_fd, b'{"command": "git commit"}')
            started = time.monotonic()
            self.assertEqual(hooks.read_payload(reader), {"command": "git commit"})
            self.assertLess(time.monotonic() - started, 1.0)
        finally:
            reader.close()
            os.close(write_fd)

    def test_hook_process_exits_when_the_host_keeps_stdin_open(self):
        self._init_git("main")
        env = dict(os.environ, LAZYPLAN_DB=str(self.db))
        Store(self.db).add_plan("P")
        proc = subprocess.Popen(
            [sys.executable, "-m", "lazyplan", "hook", "stop", "--host", "claude"],
            cwd=self.repo,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert proc.stdin is not None
        try:
            proc.stdin.write(b'{"session_id": "s1", "hook_event_name": "Stop"}')
            proc.stdin.flush()
            code = proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            self.fail("lpui hook did not exit while stdin stayed open")
        finally:
            proc.stdin.close()
            for stream in (proc.stdout, proc.stderr):
                if stream is not None:
                    stream.close()
        self.assertEqual(code, 0)
        rows = Store(self.db).list_sessions(open_only=True)
        self.assertEqual([row.host_session for row in rows], ["s1"])

    def test_hook_probe_writes_nothing_without_a_database(self):
        missing = self.home / "missing.db"
        out = io.StringIO()
        with redirect_stdout(out):
            code = lpui_main(["--db", str(missing), "hook", "--check", "--json"])
        self.assertEqual(code, 0)
        report = json.loads(out.getvalue())
        self.assertFalse(report["ok"])
        self.assertFalse(missing.exists())

    def test_hook_probe_does_not_require_an_event(self):
        args = build_parser().parse_args(["--db", "missing.db", "hook", "--check"])
        self.assertIsNone(args.event)

    def test_hook_probe_reports_an_existing_database(self):
        Store(self.db).add_plan("P")
        report = hooks.probe(Store(self.db), self.repo)
        self.assertTrue(report["ok"])
        self.assertEqual(report["db"], str(self.db))

    def test_detect_host_from_payload_and_explicit(self):
        self.assertEqual(hooks.detect_host({}, "codex"), "codex")
        self.assertEqual(hooks.detect_host({"hook_event_name": "SessionStart"}), "claude")
        self.assertEqual(hooks.detect_host({"workspace_roots": []}), "cursor")

    def _hook(self, event: str, payload: dict) -> hooks.HookResult:
        return hooks.build_result(
            event,
            payload,
            self.repo,
            commits=[],
            store=Store(self.db),
            host="opencode",
        )

    def test_each_host_session_gets_its_own_row(self):
        for name in ("host-a", "host-b", "host-c"):
            self._hook("prompt-submit", {"host_session": name})
        sessions = Store(self.db).list_sessions(open_only=True)
        self.assertEqual(len(sessions), 3)
        self.assertEqual(
            {session.host_session for session in sessions},
            {"host-a", "host-b", "host-c"},
        )
        self.assertEqual(len({session.id for session in sessions}), 3)

    def test_stop_and_end_events_touch_only_the_firing_row(self):
        for name in ("host-a", "host-b", "host-c"):
            self._hook("prompt-submit", {"host_session": name})
        store = Store(self.db)
        ids = {row.host_session: row.id for row in store.list_sessions(open_only=True)}
        self._hook("stop", {"host_session": "host-a"})
        store = Store(self.db)
        stopped = store.get_session(ids["host-a"])
        assert stopped is not None
        self.assertTrue(stopped.awaiting)
        for name in ("host-b", "host-c"):
            other = store.get_session(ids[name])
            assert other is not None
            self.assertFalse(other.awaiting)
            self.assertFalse(other.ended)
        self._hook("session-end", {"host_session": "host-a"})
        store = Store(self.db)
        ended = store.get_session(ids["host-a"])
        assert ended is not None
        self.assertTrue(ended.ended)
        for name in ("host-b", "host-c"):
            other = store.get_session(ids[name])
            assert other is not None
            self.assertFalse(other.ended)
        self._hook("session-end", {"host_session": "host-b"})
        self._hook("session-end", {"host_session": "host-c"})
        self.assertEqual(Store(self.db).list_sessions(open_only=True), [])

    def test_tool_events_refresh_only_the_firing_row(self):
        for name in ("host-a", "host-b"):
            self._hook("prompt-submit", {"host_session": name})
        before = {
            row.host_session: row.last_seen_at
            for row in Store(self.db).list_sessions(open_only=True)
        }
        time.sleep(0.02)
        self._hook("pre-tool", {"host_session": "host-b", "command": "ls"})
        after = {
            row.host_session: row.last_seen_at
            for row in Store(self.db).list_sessions(open_only=True)
        }
        self.assertEqual(after["host-a"], before["host-a"])
        self.assertGreater(after["host-b"], before["host-b"])

    def test_a_tool_event_opens_a_row_but_end_without_one_does_not(self):
        self._hook("pre-tool", {"host_session": "host-a", "command": "ls"})
        store = Store(self.db)
        rows = store.list_sessions(open_only=True)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].host_session, "host-a")
        self._hook("session-end", {"host_session": "host-x"})
        self.assertEqual(len(Store(self.db).list_sessions(open_only=True)), 1)

    def test_a_concrete_session_does_not_adopt_a_manual_row(self):
        manual, _ = Store(self.db).start_session("agent", now=time.time())
        self._hook("prompt-submit", {"host_session": "host-a"})
        rows = Store(self.db).list_sessions(open_only=True)
        self.assertEqual(len(rows), 2)
        host_row = next(row for row in rows if row.host_session == "host-a")
        self.assertNotEqual(host_row.id, manual.id)
        kept = Store(self.db).get_session(manual.id)
        assert kept is not None
        self.assertFalse(kept.ended)

    def test_session_start_records_the_branch_and_its_plan(self):
        plan_id, task_id = self._seed()
        self._init_git(f"task/{task_id}-pane")
        hooks.build_result(
            "session-start", {"session_id": "host-a"}, self.repo, commits=[], store=Store(self.db)
        )
        row = Store(self.db).list_sessions(open_only=True)[0]
        self.assertEqual(row.branch, f"task/{task_id}-pane")
        self.assertEqual(row.plan_id, plan_id)

    def test_a_branch_switch_updates_the_row(self):
        plan_id, task_id = self._seed()
        self._init_git("main")
        store = Store(self.db)
        hooks.build_result(
            "session-start", {"session_id": "host-a"}, self.repo, commits=[], store=store
        )
        started = Store(self.db).list_sessions(open_only=True)[0]
        self.assertEqual(started.branch, "main")
        self._git("switch", "-c", f"task/{task_id}-pane")
        hooks.build_result(
            "prompt-submit", {"session_id": "host-a"}, self.repo, commits=[], store=store
        )
        updated = Store(self.db).get_session(started.id)
        assert updated is not None
        self.assertEqual(updated.branch, f"task/{task_id}-pane")
        self.assertEqual(updated.plan_id, plan_id)

    def test_a_manual_plan_survives_a_branch_switch(self):
        plan_id, _task_id = self._seed()
        store = Store(self.db)
        other = store.add_plan("Other", actor="ana")
        milestone = store.add_milestone(other.id, "Other milestone", actor="ana")
        other_task = store.add_task(milestone.id, "Other task", actor="ana")
        self._init_git("main")
        session, _ = store.start_session(
            "ana",
            plan_id=plan_id,
            repo_path=str(self.repo),
            branch="main",
            plan_source="manual",
        )
        store.bind_session(
            "opencode",
            "host-a",
            git_common_dir(str(self.repo)),
            str(self.repo),
            session.id,
        )
        self._git("switch", "-c", f"task/{other_task.id}-other")
        hooks.build_result(
            "prompt-submit", {"session_id": "host-a"}, self.repo, commits=[], store=store
        )
        updated = Store(self.db).get_session(session.id)
        assert updated is not None
        self.assertEqual(updated.plan_id, plan_id)
        self.assertEqual(updated.branch, f"task/{other_task.id}-other")

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

    def test_heartbeat_reap_uses_each_phases_window(self):
        now = time.time()
        store = Store(self.db)
        working, _ = store.start_session(
            "ana", now=now - 700, phase="working", repo_path=str(self.repo)
        )
        awaiting, _ = store.start_session(
            "bo", now=now - 700, phase="awaiting", repo_path=str(self.repo)
        )
        self._hook("prompt-submit", {"host_session": "new"})
        store = Store(self.db)
        closed = store.get_session(working.id)
        open_row = store.get_session(awaiting.id)
        assert closed is not None and open_row is not None
        self.assertTrue(closed.ended)
        self.assertTrue(closed.auto_closed)
        self.assertFalse(open_row.ended)

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
        _plan, task_id = self._seed_linked()
        payload = {"tool_input": {"command": "git commit -m x"}}
        result = hooks.build_result(
            "post-tool", payload, self.repo, commits=[], store=Store(self.db)
        )
        self.assertIn(f"--id {task_id}", result.text)
        self.assertTrue(result.context)

    def test_post_tool_names_a_global_plans_doing_task(self):
        _plan, task_id = self._seed()
        payload = {"tool_input": {"command": "git commit -m x"}}
        result = hooks.build_result(
            "post-tool", payload, self.repo, commits=[], store=Store(self.db)
        )
        self.assertIn(f"--id {task_id}", result.text)

    def test_post_tool_with_nothing_in_progress_is_silent_outside_a_managed_checkout(self):
        Store(self.db).add_plan("Idle", "what", goal="why")
        for payload in (
            {"tool_input": {"command": "git commit -m x"}},
            {"tool_name": "Edit", "tool_input": {"file_path": "src/app.py"}},
        ):
            with self.subTest(payload=payload):
                result = hooks.build_result(
                    "post-tool", payload, self.repo, commits=[], store=Store(self.db)
                )
                self.assertEqual(result.text, "")

    def test_cli_post_tool_reminder_reaches_claude_as_context(self):
        _plan, task_id = self._seed_linked()
        out = io.StringIO()
        old_stdin = sys.stdin
        sys.stdin = io.StringIO(
            json.dumps({"hook_event_name": "PostToolUse", "tool_input": {"command": "git commit"}})
        )
        try:
            with redirect_stdout(out):
                code = lpui_main(["hook", "post-tool", "--host", "claude"])
        finally:
            sys.stdin = old_stdin
        self.assertEqual(code, 0)
        body = json.loads(out.getvalue())
        self.assertNotIn("systemMessage", body)
        self.assertEqual(body["hookSpecificOutput"]["hookEventName"], "PostToolUse")
        self.assertIn(f"--id {task_id}", body["hookSpecificOutput"]["additionalContext"])

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

    def test_a_host_session_in_an_unrelated_checkout_does_not_gate_commits(self):
        self._seed()
        payload = {"session_id": "s-1", "hook_event_name": "PreToolUse"}
        for event in ("session-start", "prompt-submit"):
            hooks.build_result(
                event, payload, self.repo, commits=[], store=Store(self.db), host="claude"
            )
        commit = dict(payload, tool_input={"command": "git commit -m x"})
        result = hooks.build_result(
            "pre-tool", commit, self.repo, commits=[], store=Store(self.db), host="claude"
        )
        self.assertEqual(result, hooks.HookResult())
        self.assertEqual(len(Store(self.db).list_sessions(open_only=True)), 1)

    def test_non_git_commands_are_never_blocked(self):
        self._linked_plan()
        payload = {"tool_input": {"command": "git status"}}
        result = hooks.build_result(
            "pre-tool", payload, self.repo, commits=[], store=Store(self.db), mode="strict"
        )
        self.assertEqual(result.block, "")

    def test_post_tool_edit_names_the_owning_task(self):
        _plan, task_id = self._seed_linked()
        Store(self.db).add_touchpoint(task_id, "src/**", actor="t")
        payload = {"tool_name": "Edit", "tool_input": {"file_path": "src/app.py"}}
        result = hooks.build_result(
            "post-tool", payload, self.repo, commits=[], store=Store(self.db)
        )
        self.assertIn(f"T{task_id}", result.text)

    def test_post_tool_absolute_edit_path_names_the_owning_task(self):
        _plan, task_id = self._seed_linked()
        Store(self.db).add_touchpoint(task_id, "src/**", actor="t")
        absolute = str(self.repo / "src" / "app.py")
        payload = {"tool_name": "Edit", "tool_input": {"file_path": absolute}}
        result = hooks.build_result(
            "post-tool", payload, self.repo, commits=[], store=Store(self.db)
        )
        self.assertIn(f"src/app.py belongs to T{task_id}", result.text)

    def test_post_tool_edit_outside_the_checkout_keeps_its_path(self):
        _plan, task_id = self._seed_linked()
        Store(self.db).add_touchpoint(task_id, "src/**", actor="t")
        outside = self.home / "src" / "app.py"
        payload = {"tool_name": "Write", "tool_input": {"file_path": str(outside)}}
        result = hooks.build_result(
            "post-tool", payload, self.repo, commits=[], store=Store(self.db)
        )
        self.assertNotIn("belongs to", result.text)
        self.assertIn(outside.as_posix(), result.text)

    def test_post_tool_edit_outside_the_task_asks_for_scope(self):
        _plan, _task = self._seed_linked()
        payload = {"tool_name": "Write", "tool_input": {"file_path": "docs/readme.md"}}
        result = hooks.build_result(
            "post-tool", payload, self.repo, commits=[], store=Store(self.db)
        )
        self.assertIn("scope", result.text)

    def test_post_tool_apply_patch_reads_the_patch_path(self):
        _plan, task_id = self._seed_linked()
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
        self._linked_plan()
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

    def test_cli_command_flag_reaches_the_commit_gate(self):
        self._linked_plan()
        out = io.StringIO()
        old_stdin = sys.stdin
        sys.stdin = io.StringIO("")
        try:
            with redirect_stdout(out):
                code = lpui_main(
                    [
                        "hook",
                        "pre-tool",
                        "--host",
                        "opencode",
                        "--mode",
                        "strict",
                        "--command",
                        "git commit -m x",
                        "--json",
                    ]
                )
        finally:
            sys.stdin = old_stdin
        self.assertEqual(code, 0)
        self.assertIn("no doing task", json.loads(out.getvalue())["block"])

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
