"""Append-only handoff notes across rows, show/brief, and export/import."""

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
from lazyplan.store import Store  # noqa: E402


class TestNotes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "notes.db")
        store = Store(self.db)
        plan = store.add_plan("P", "what", goal="why", actor="fixture")
        milestone = store.add_milestone(plan.id, "M", actor="fixture")
        store.add_task(milestone.id, "T1", description="first", actor="fixture")
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

    def test_add_and_list_notes(self):
        note = self._json(
            "note", "add", "--kind", "task", "--id", "1", "--text", "Decision: keep it"
        )
        self.assertEqual(note["note"]["actor"], "alice")
        self.assertEqual(note["note"]["text"], "Decision: keep it")
        listed = self._json("note", "list", "--kind", "task", "--id", "1")
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["text"], "Decision: keep it")

    def test_empty_note_is_rejected(self):
        code, out, err = self._run("note", "add", "--kind", "task", "--id", "1", "--text", "  ")
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("needs --text", err)

    def test_notes_are_ordered_oldest_first_and_limit_latest(self):
        for text in ("one", "two", "three"):
            self._json("note", "add", "--kind", "task", "--id", "1", "--text", text)
        listed = self._json("note", "list", "--kind", "task", "--id", "1")
        self.assertEqual([n["text"] for n in listed], ["one", "two", "three"])
        latest = self._json("note", "list", "--kind", "task", "--id", "1", "--limit", "2")
        self.assertEqual([n["text"] for n in latest], ["two", "three"])

    def test_show_and_brief_include_notes(self):
        self._json("note", "add", "--kind", "plan", "--id", "1", "--text", "Plan note")
        self._json("claim", "--id", "1")
        self._json("note", "add", "--kind", "task", "--id", "1", "--text", "Task note")

        code, out, err = self._run("task", "show", "--id", "1")
        self.assertEqual(code, 0, err)
        self.assertIn("Task note", out)
        code, out, err = self._run("--porcelain", "task", "show", "--id", "1")
        self.assertEqual(code, 0, err)
        self.assertIn("note\t", out)
        self.assertIn("Task note", out)

        payload = self._json("brief", "--plan", "1")
        plan = payload["plans"][0]
        self.assertEqual(plan["notes"][0]["text"], "Plan note")
        self.assertEqual(plan["doing"][0]["notes"][0]["text"], "Task note")
        code, out, err = self._run("brief", "--plan", "1")
        self.assertIn("Plan note", out)
        self.assertIn("Task note", out)

    def test_note_rows_in_porcelain(self):
        code, out, err = self._run(
            "--porcelain", "note", "add", "--kind", "task", "--id", "1", "--text", "Hi"
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(out.rstrip("\n").split("\t")[:5], ["note", "1", "alice", "Hi", "task:1"])
        code, out, err = self._run("--porcelain", "note", "list", "--kind", "task", "--id", "1")
        self.assertEqual(code, 0, err)
        self.assertIn("note\t1\talice\tHi\ttask:1\t", out)

    def test_deleting_a_parent_removes_notes(self):
        store = Store(self.db)
        store.add_note("task", 1, "gone", actor="fixture")
        self.assertTrue(store.delete("task", 1))
        self.assertEqual(store.list_notes("task", 1), [])

    def test_export_import_preserves_notes(self):
        store = Store(self.db)
        store.add_note("task", 1, "keep me", actor="fixture")
        data = services.export_all(store)
        notes = data["plans"][0]["milestones"][0]["tasks"][0]["notes"]
        self.assertEqual(notes[0]["text"], "keep me")
        other = Store(os.path.join(self.tmp.name, "other.db"))
        counts = services.import_all(other, data, actor="fixture")
        self.assertEqual(counts["notes"], 1)
        self.assertEqual(other.list_notes("task", 1)[0].text, "keep me")

    def test_missing_parent_is_an_error(self):
        code, out, err = self._run("note", "add", "--kind", "task", "--id", "99", "--text", "x")
        self.assertEqual(code, 1)
        self.assertIn("not found", err)


if __name__ == "__main__":
    unittest.main()
