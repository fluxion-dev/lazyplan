"""Agent CLI: exact registry rows, the hidden alias, and legacy history."""

from __future__ import annotations

import io
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from lazyplan.presentation.cli import main as lpui_main
from lazyplan.store import Store


class AgentCliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "t.db")
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=self.repo, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"], cwd=self.repo, check=True
        )
        subprocess.run(["git", "config", "user.name", "Test"], cwd=self.repo, check=True)
        (self.repo / "f").write_text("one\n", encoding="utf-8")
        subprocess.run(["git", "add", "f"], cwd=self.repo, check=True)
        subprocess.run(["git", "commit", "-qm", "init"], cwd=self.repo, check=True)
        self.old_cwd = os.getcwd()
        os.chdir(self.repo)
        self.store = Store(self.db)
        self.plan = self.store.add_plan("P", worktree_required=False)
        self.store.register_plan_worktree(self.plan.id, str(self.repo), str(self.repo))
        self.milestone = self.store.add_milestone(self.plan.id, "M")
        self.task = self.store.add_task(self.milestone.id, "T")

    def tearDown(self) -> None:
        os.chdir(self.old_cwd)
        self.tmp.cleanup()

    def _run(self, *argv: str) -> tuple[int, str, str]:
        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = lpui_main(["--db", self.db, *argv])
        return code, out.getvalue(), err.getvalue()

    def _start(self, *extra: str) -> dict:
        code, out, err = self._run(
            "--actor", "ana", "--json", "agent", "start", "--plan", str(self.plan.id), *extra
        )
        self.assertEqual(code, 0, err)
        return json.loads(out)["agent"]

    def test_agent_ids_accept_the_a_prefix(self) -> None:
        agent = self._start()
        for raw in (f"A{agent['id']}", str(agent["id"])):
            code, out, err = self._run("--json", "agent", "show", "--id", raw)
            self.assertEqual(code, 0, err)
            self.assertEqual(json.loads(out)["agent"]["id"], agent["id"])
        with self.assertRaises(SystemExit) as caught:
            self._run("agent", "show", "--id", "A0")
        self.assertEqual(caught.exception.code, 2)

    def test_json_carries_every_identity_and_context_field(self) -> None:
        agent = self._start(
            "--host", "opencode", "--session", "host-1", "--agent", "builder", "--model", "gpt-5"
        )
        for field in (
            "host",
            "host_session",
            "agent",
            "role",
            "model",
            "parent_id",
            "pid",
            "repo_path",
            "worktree",
            "branch",
            "head_sha",
            "plan_id",
            "task_id",
            "status",
            "unbound_reason",
        ):
            self.assertIn(field, agent)
        self.assertEqual(agent["plan_id"], self.plan.id)
        self.assertEqual(agent["agent"], "builder")
        self.assertEqual(agent["host"], "opencode")
        self.assertEqual(agent["host_session"], "host-1")

    def test_end_with_summary_and_show(self) -> None:
        agent = self._start()
        code, out, err = self._run(
            "--actor",
            "ana",
            "--json",
            "agent",
            "end",
            "--id",
            f"A{agent['id']}",
            "--summary",
            "shipped",
            "--handoff",
            "next: T2",
        )
        self.assertEqual(code, 0, err)
        ended = json.loads(out)["agent"]
        self.assertEqual(ended["summary"], "shipped")
        self.assertEqual(ended["handoff"], "next: T2")
        self.assertTrue(ended["ended_at"])
        code, out, err = self._run("--json", "agent", "show", "--id", str(agent["id"]))
        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertEqual(payload["agent"]["status"], "ended")
        self.assertTrue(payload["events"])

    def test_show_without_id_uses_the_current_agent(self) -> None:
        agent = self._start()
        code, out, err = self._run("--actor", "ana", "--json", "agent", "show")
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["agent"]["id"], agent["id"])

    def test_text_porcelain_and_open_filters(self) -> None:
        first = self._start()
        code, out, err = self._run("--actor", "ana", "agent", "list")
        self.assertEqual(code, 0, err)
        self.assertIn(f"A{first['id']} [starting]", out)
        code, out, err = self._run("--actor", "ana", "--porcelain", "agent", "list")
        self.assertEqual(code, 0, err)
        self.assertEqual(out.split("\t")[0], "agent")
        self._run("--actor", "ana", "agent", "end", "--id", str(first["id"]))
        code, out, err = self._run("--actor", "ana", "--json", "agent", "list", "--open")
        self.assertEqual(json.loads(out), [])

    def test_porcelain_list_carries_the_worktree(self) -> None:
        self._start("--host", "opencode", "--session", "ses_7f3a")
        code, out, err = self._run("--actor", "agent", "--porcelain", "agent", "list")
        self.assertEqual(code, 0, err)
        self.assertIn(str(self.repo), out)

    def test_start_twice_updates_the_same_host_row(self) -> None:
        first = self._start("--host", "opencode", "--session", "host-1")
        second = self._start("--host", "opencode", "--session", "host-1")
        self.assertEqual(first["id"], second["id"])

    def test_second_manual_start_creates_a_distinct_row(self) -> None:
        first = self._start()
        second = self._start()
        self.assertNotEqual(first["id"], second["id"])

    def test_unregistered_worktree_is_refused_without_a_row(self) -> None:
        self.store.remove_plan_worktree(self.plan.id, str(self.repo))
        code, _, err = self._run("--actor", "ana", "agent", "start", "--plan", str(self.plan.id))
        self.assertEqual(code, 2)
        self.assertIn("registered worktree", err)
        self.assertEqual(self.store.list_agents(), [])

    def test_hidden_session_alias_starts_and_lists_agents(self) -> None:
        code, out, err = self._run(
            "--actor", "ana", "--json", "session", "start", "--plan", str(self.plan.id)
        )
        self.assertEqual(code, 0, err)
        session = json.loads(out)["session"]
        self.assertEqual(session["plan_id"], self.plan.id)
        code, out, err = self._run("--actor", "ana", "--porcelain", "session", "list")
        self.assertEqual(code, 0, err)
        self.assertEqual(out.split("\t")[0], "agent")
        code, out, err = self._run(
            "--actor", "ana", "--json", "session", "end", "--summary", "done"
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["session"]["summary"], "done")

    def test_history_keeps_original_s_ids_and_feed_filter(self) -> None:
        self.store.restore_session_history(
            {
                "id": 7,
                "actor": "ana",
                "plan_id": self.plan.id,
                "started_at": 100.0,
                "ended_at": 200.0,
                "summary": "old work",
                "handoff": "next: T2",
            }
        )
        self.store.log("ana", "plan", "edit", "renamed", session_id=7)
        code, out, err = self._run("--json", "agent", "history")
        self.assertEqual(code, 0, err)
        self.assertEqual([row["id"] for row in json.loads(out)], [7])
        code, out, err = self._run("--json", "agent", "show", "--id", "S7")
        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertTrue(payload["history"])
        self.assertEqual(payload["session"]["summary"], "old work")
        code, out, err = self._run("--json", "feed", "--session", "7")
        self.assertEqual(code, 0, err)
        events = json.loads(out)
        self.assertTrue(events)
        self.assertTrue(all(event["session_id"] == 7 for event in events))

    def test_unknown_rows(self) -> None:
        code, _, err = self._run("--json", "agent", "show", "--id", "99")
        self.assertEqual(code, 1)
        self.assertIn("not found", err)
        code, _, err = self._run("--json", "agent", "show", "--id", "S99")
        self.assertEqual(code, 1)
        self.assertIn("not found", err)
        code, _, err = self._run("--actor", "ana", "--json", "agent", "end")
        self.assertEqual(code, 1)

    def test_reads_without_database_do_not_create_one(self) -> None:
        missing = os.path.join(self.tmp.name, "missing.db")
        out = io.StringIO()
        with redirect_stdout(out):
            code = lpui_main(["--db", missing, "agent", "list"])
        self.assertEqual(code, 0)
        self.assertIn("no agents", out.getvalue())
        self.assertFalse(os.path.exists(missing))


if __name__ == "__main__":
    unittest.main()
