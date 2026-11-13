"""Session CLI: start, end, show, list, and feed filtering."""

from __future__ import annotations

import io
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from lazyplan.presentation.cli import main as lpui_main
from lazyplan.store import Store


class SessionCliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "t.db")
        self.store = Store(self.db)
        self.plan = self.store.add_plan("P", worktree_required=False)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _run(self, *argv: str) -> tuple[int, str, str]:
        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = lpui_main(["--db", self.db, *argv])
        return code, out.getvalue(), err.getvalue()

    def _start(self, *extra: str) -> dict:
        code, out, err = self._run(
            "--actor", "ana", "--json", "session", "start", "--plan", str(self.plan.id), *extra
        )
        self.assertEqual(code, 0, err)
        return json.loads(out)["session"]

    def test_session_ids_accept_the_s_prefix(self) -> None:
        session = self._start()
        for raw in (f"S{session['id']}", str(session["id"])):
            code, out, err = self._run("--json", "session", "show", "--id", raw)
            self.assertEqual(code, 0, err)
            self.assertEqual(json.loads(out)["session"]["id"], session["id"])
        with self.assertRaises(SystemExit) as caught:
            self._run("session", "show", "--id", "S0")
        self.assertEqual(caught.exception.code, 2)

    def test_start_tags_writes_and_feed_filters(self) -> None:
        session = self._start()
        self.assertEqual(session["ended_at"], 0)
        code, out, err = self._run(
            "--actor", "ana", "--json", "plan", "edit", "--id", "1", "--title", "Renamed"
        )
        self.assertEqual(code, 0, err)
        code, out, err = self._run("--json", "feed", "--session", str(session["id"]))
        self.assertEqual(code, 0, err)
        events = json.loads(out)
        self.assertTrue(events)
        self.assertTrue(all(event["session_id"] == session["id"] for event in events))

    def test_end_with_summary_and_show(self) -> None:
        session = self._start()
        code, out, err = self._run(
            "--actor",
            "ana",
            "--json",
            "session",
            "end",
            "--summary",
            "shipped",
            "--handoff",
            "next: T2",
        )
        self.assertEqual(code, 0, err)
        ended = json.loads(out)["session"]
        self.assertEqual(ended["summary"], "shipped")
        self.assertGreater(ended["ended_at"], 0)
        code, out, err = self._run("--json", "session", "show", "--id", str(session["id"]))
        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertEqual(payload["session"]["handoff"], "next: T2")
        self.assertIn("start", payload["counts"])

    def test_show_without_id_uses_the_active_session(self) -> None:
        session = self._start()
        code, out, err = self._run("--actor", "ana", "--json", "session", "show")
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["session"]["id"], session["id"])

    def test_text_and_porcelain_list(self) -> None:
        session = self._start()
        code, out, err = self._run("--actor", "ana", "session", "list")
        self.assertEqual(code, 0, err)
        self.assertIn(f"S{session['id']} [working]", out)
        code, out, err = self._run("--actor", "ana", "--porcelain", "session", "list")
        self.assertEqual(code, 0, err)
        self.assertEqual(out.split("\t")[0], "session")

    def test_text_list_shows_plan_title_task_and_branch(self) -> None:
        self._start("--branch", "task/157-pane")
        code, out, err = self._run("--actor", "ana", "session", "list")
        self.assertEqual(code, 0, err)
        self.assertIn(f"P{self.plan.id}", out)
        self.assertIn("T157", out)
        self.assertIn("on task/157-pane", out)

    def test_a_plan_less_row_never_prints_pnone(self) -> None:
        self.store.start_session("ana")
        code, out, err = self._run("--actor", "ana", "session", "list", "--all")
        self.assertEqual(code, 0, err)
        self.assertNotIn("PNone", out)
        self.assertIn("ana -", out)

    def test_start_without_flags_records_the_checkout_branch(self) -> None:
        milestone = self.store.add_milestone(self.plan.id, "M")
        task = self.store.add_task(milestone.id, "T")
        repo = Path(self.tmp.name) / "repo"
        repo.mkdir()
        for args in (
            ("init", "-b", f"task/{task.id}-pane"),
            ("config", "user.email", "test@example.com"),
            ("config", "user.name", "Test"),
        ):
            subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)
        (repo / "file.txt").write_text("one\n", encoding="utf-8")
        for args in (("add", "file.txt"), ("commit", "-m", "init")):
            subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)
        with mock.patch("lazyplan.infrastructure.checkout.checkout_path", return_value=str(repo)):
            code, out, err = self._run("--actor", "ana", "--json", "session", "start")
        self.assertEqual(code, 0, err)
        session = json.loads(out)["session"]
        self.assertEqual(session["branch"], f"task/{task.id}-pane")
        self.assertEqual(session["plan_id"], self.plan.id)
        self.assertEqual(session["plan_source"], "auto")

    def test_an_explicit_plan_is_marked_manual(self) -> None:
        session = self._start()
        self.assertEqual(session["plan_source"], "manual")

    def test_list_shows_the_short_host_session(self) -> None:
        self.store.start_session(
            "agent",
            plan_id=self.plan.id,
            host="opencode",
            host_session="ses_7f3a",
        )
        code, out, err = self._run("--actor", "agent", "session", "list")
        self.assertEqual(code, 0, err)
        self.assertIn("via opencode", out)
        self.assertIn("7f3a", out)
        code, out, err = self._run("--json", "session", "list", "--all")
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)[0]["host_session"], "ses_7f3a")

    def test_second_start_needs_force(self) -> None:
        first = self._start()
        code, _out, err = self._run(
            "--actor", "ana", "--json", "session", "start", "--plan", str(self.plan.id)
        )
        self.assertEqual(code, 2)
        self.assertIn("already open", err)
        code, out, err = self._run(
            "--actor", "ana", "--json", "session", "start", "--plan", str(self.plan.id), "--force"
        )
        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertEqual(payload["previous"]["id"], first["id"])
        self.assertGreater(payload["previous"]["ended_at"], 0)

    def test_unknown_and_ended_sessions(self) -> None:
        code, _out, err = self._run("--json", "session", "show", "--id", "99")
        self.assertEqual(code, 1)
        session = self._start()
        self._run("--actor", "ana", "--json", "session", "end")
        code, _out, err = self._run(
            "--actor", "ana", "--json", "session", "end", "--id", str(session["id"])
        )
        self.assertEqual(code, 1)
        self.assertIn("already ended", err)

    def test_reads_without_database_do_not_create_one(self) -> None:
        missing = os.path.join(self.tmp.name, "missing.db")
        out = io.StringIO()
        with redirect_stdout(out):
            code = lpui_main(["--db", missing, "session", "list"])
        self.assertEqual(code, 0)
        self.assertIn("no sessions", out.getvalue())
        self.assertFalse(os.path.exists(missing))


if __name__ == "__main__":
    unittest.main()
