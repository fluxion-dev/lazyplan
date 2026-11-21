"""Draft-first creation: plan add and plan apply draft unless --direct --reason."""

from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from lazyplan.presentation.cli import main as lpui_main
from lazyplan.services.sketch_document import parse_sketch
from lazyplan.store import Store

from .test_drafts import document


class DraftFirstCliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "t.db")
        self.store = Store(self.db)
        self.path = os.path.join(self.tmp.name, "plan.json")
        with open(self.path, "w", encoding="utf-8") as handle:
            json.dump(document(), handle)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _run(self, *argv: str) -> tuple[int, str, str]:
        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = lpui_main(["--db", self.db, "--actor", "agent", *argv])
        return code, out.getvalue(), err.getvalue()

    def _add(self, *extra: str) -> tuple[int, str, str]:
        return self._run(
            "--json", "plan", "add", "--title", "API v2", "--why", "w", "--what", "x", *extra
        )

    def test_plan_add_creates_a_draft_and_no_plan(self) -> None:
        code, out, err = self._add()
        self.assertEqual(code, 0, err)
        draft = json.loads(out)["draft"]
        self.assertEqual(draft["status"], "review")
        self.assertEqual(self.store.list_plans(), [])

    def test_plan_add_creates_independent_sketches(self) -> None:
        self._add()
        code, out, err = self._add()
        self.assertEqual(code, 0, err)
        stored = self.store.get_draft(json.loads(out)["draft"]["id"])
        assert stored is not None
        self.assertEqual(stored.format, "sketch")
        sketch = parse_sketch(stored.document)
        self.assertEqual(sketch.title, "API v2")
        self.assertEqual(sketch.why, "w")
        self.assertEqual(sketch.what, "x")

    def test_plan_add_without_why_is_refused(self) -> None:
        code, _out, err = self._run("plan", "add", "--title", "Bare")
        self.assertEqual(code, 2)
        self.assertIn("why must not be empty", err)
        self.assertEqual(self.store.list_drafts(), [])

    def test_plan_apply_creates_a_draft_and_no_plan(self) -> None:
        code, out, err = self._run("--json", "plan", "apply", "--file", self.path)
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["draft"]["title"], "Demo plan")
        self.assertEqual(self.store.list_plans(), [])

    def test_plan_apply_refuses_a_key_already_in_a_draft(self) -> None:
        self._run("plan", "apply", "--file", self.path)
        code, _out, err = self._run("plan", "apply", "--file", self.path)
        self.assertEqual(code, 2)
        self.assertIn("already in draft #1", err)

    def test_direct_without_reason_is_refused(self) -> None:
        for argv in (
            ("plan", "add", "--title", "P", "--why", "w", "--what", "x", "--direct"),
            ("plan", "apply", "--file", self.path, "--direct"),
            ("plan", "apply", "--file", self.path, "--direct", "--reason", "  "),
        ):
            with self.subTest(argv=argv):
                code, _out, err = self._run(*argv)
                self.assertEqual(code, 2)
                self.assertIn("--direct needs --reason", err)
        self.assertEqual(self.store.list_plans(), [])
        self.assertEqual(self.store.list_drafts(), [])

    def test_direct_with_reason_creates_a_plan_and_notes_why(self) -> None:
        for argv in (
            ("plan", "add", "--title", "P", "--direct", "--reason", "bulk import"),
            ("plan", "apply", "--file", self.path, "--direct", "--reason", "bulk import"),
        ):
            with self.subTest(argv=argv):
                code, out, err = self._run("--json", *argv)
                self.assertEqual(code, 0, err)
                plan_id = json.loads(out)["plan"]["id"]
                notes = [note.text for note in self.store.list_notes("plan", plan_id)]
                self.assertEqual(notes, ["Skipped draft review (agent): bulk import"])
        self.assertEqual(self.store.list_drafts(), [])

    def test_promoted_draft_is_the_queued_plan(self) -> None:
        code, out, err = self._run("--json", "plan", "apply", "--file", self.path)
        draft_id = json.loads(out)["draft"]["id"]
        code, out, err = self._run("--json", "draft", "promote", "--id", str(draft_id))
        self.assertEqual(code, 0, err)
        self.assertEqual([plan.name for plan in self.store.list_plans()], ["Demo plan"])


if __name__ == "__main__":
    unittest.main()
