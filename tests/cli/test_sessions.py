"""Session CLI: start, end, show, list, and feed filtering."""

from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from lazyplan.presentation.cli import main as lpui_main
from lazyplan.store import Store


class SessionCliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "t.db")
        self.store = Store(self.db)
        self.plan = self.store.add_plan("P")

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
        self.assertIn(f"S{session['id']} [open]", out)
        code, out, err = self._run("--actor", "ana", "--porcelain", "session", "list")
        self.assertEqual(code, 0, err)
        self.assertEqual(out.split("\t")[0], "session")

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
