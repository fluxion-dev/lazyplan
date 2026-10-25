"""Blocked tasks: claim release, next skipping, visibility, and export."""

from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from lazyplan import services  # noqa: E402
from lazyplan.cli import main as lpui_main  # noqa: E402
from lazyplan.models import Status  # noqa: E402
from lazyplan.store import Store  # noqa: E402


class TestBlockedTasks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "blocked.db")
        store = Store(self.db)
        plan = store.add_plan("P", "what", goal="why", actor="fixture")
        milestone = store.add_milestone(plan.id, "M", actor="fixture")
        store.add_task(milestone.id, "T1", description="first", actor="fixture")
        store.add_task(milestone.id, "T2", description="second", actor="fixture")
        self.old_home = os.environ.get("HOME")
        self.old_setup = os.environ.get("LAZYPLAN_NO_SETUP")
        os.environ["HOME"] = self.tmp.name
        os.environ["LAZYPLAN_NO_SETUP"] = "1"

    def tearDown(self):
        for key, value in (("HOME", self.old_home), ("LAZYPLAN_NO_SETUP", self.old_setup)):
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()

    def _run(self, *argv: str, actor: str = "alice") -> tuple[int, str, str]:
        out = io.StringIO()
        err = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = lpui_main(["--db", self.db, "--actor", actor, *argv])
        return code, out.getvalue(), err.getvalue()

    def _json(self, *argv: str, actor: str = "alice") -> object:
        code, out, err = self._run("--json", *argv, actor=actor)
        self.assertEqual(code, 0, err)
        return json.loads(out)

    def test_block_releases_the_claim_and_moves_doing_to_todo(self):
        self._json("claim", "--id", "1")
        result = self._json("task", "block", "--id", "1", "--reason", "waiting on design")
        self.assertTrue(result["task"]["blocked"])
        self.assertEqual(result["task"]["blocked_reason"], "waiting on design")
        self.assertEqual(result["task"]["status"], "todo")
        store = Store(self.db)
        self.assertIsNone(store.get_claim(1))
        notes = store.list_notes("task", 1)
        self.assertEqual(notes[-1].text, "Blocked: waiting on design")

    def test_next_and_claim_skip_blocked_tasks(self):
        self._json("task", "block", "--id", "1", "--reason", "waiting")
        result = self._json("next")
        self.assertEqual(result["task"]["id"], 2)
        code, _, err = self._run("claim", "--id", "1")
        self.assertEqual(code, 2)
        self.assertIn("blocked", err)

    def test_unblock_returns_the_task_to_the_pool(self):
        self._json("task", "block", "--id", "1", "--reason", "waiting")
        result = self._json("task", "unblock", "--id", "1")
        self.assertFalse(result["task"].get("blocked", False))
        self.assertEqual(result["task"].get("blocked_reason", ""), "")
        self.assertEqual(self._json("next")["task"]["id"], 1)

    def test_block_porcelain_marks_the_task_row(self):
        code, out, err = self._run(
            "--porcelain", "task", "block", "--id", "1", "--reason", "waiting"
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(
            out.rstrip("\n").split("\t"),
            ["task", "1", "todo", "T1", "milestone:1", "blocked"],
        )
        code, out, err = self._run("--porcelain", "task", "unblock", "--id", "1")
        self.assertEqual(code, 0, err)
        self.assertEqual(
            out.rstrip("\n").split("\t"), ["task", "1", "todo", "T1", "milestone:1", "-"]
        )

    def test_show_and_tree_name_the_block(self):
        self._json("task", "block", "--id", "1", "--reason", "waiting on design")
        code, out, err = self._run("task", "show", "--id", "1")
        self.assertEqual(code, 0, err)
        self.assertIn("blocked: waiting on design", out)
        code, out, err = self._run("task", "list", "--milestone", "1")
        self.assertEqual(code, 0, err)
        self.assertIn("[blocked]", out)

    def test_brief_next_skips_blocked(self):
        self._json("task", "block", "--id", "1", "--reason", "waiting")
        payload = self._json("brief", "--plan", "1")
        self.assertEqual(payload["plans"][0]["next"]["id"], 2)

    def test_blocking_a_done_task_is_rejected(self):
        store = Store(self.db)
        services.set_status(store, "task", 1, Status.DONE, actor="fixture")
        code, out, err = self._run("task", "block", "--id", "1", "--reason", "late")
        self.assertEqual(code, 2)
        self.assertIn("done", err)

    def test_export_and_import_preserve_blocked_state(self):
        self._json("task", "block", "--id", "1", "--reason", "waiting")
        data = services.export_all(Store(self.db))
        task = data["plans"][0]["milestones"][0]["tasks"][0]["task"]
        self.assertTrue(task["blocked"])
        other = Store(os.path.join(self.tmp.name, "other.db"))
        services.import_all(other, data, actor="fixture")
        imported = other.get_task(1)
        assert imported is not None
        self.assertTrue(imported.blocked)
        self.assertEqual(imported.blocked_reason, "waiting")


if __name__ == "__main__":
    unittest.main()
