"""Noun-first CLI edits for criteria and comments."""

from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout

from lazyplan.presentation.cli.main import main as lpui_main
from lazyplan.store import Store


class CriterionAndCommentEditTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "edit.db")
        self.env = {"LAZYPLAN_NO_SETUP": "1", "LAZYPLAN_NO_UPDATE_CHECK": "1"}
        self.saved = {key: os.environ.get(key) for key in self.env}
        os.environ.update(self.env)
        store = Store(self.db)
        self.plan = store.add_plan("Edits", "What", goal="Why")
        self.criterion = store.add_criteria("plan", self.plan.id, "Old text")
        self.comment = store.add_comment("plan", self.plan.id, "Old comment")

    def tearDown(self) -> None:
        for key, value in self.saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()

    def _run(self, argv: list[str]) -> tuple[int, str]:
        out = io.StringIO()
        with redirect_stdout(out):
            code = lpui_main(["--db", self.db, *argv])
        return code, out.getvalue()

    def test_criterion_edit_rewrites_the_text(self) -> None:
        code, output = self._run(
            ["--json", "criterion", "edit", "--id", str(self.criterion.id), "--text", "New text"]
        )
        self.assertEqual(code, 0)
        self.assertEqual(Store(self.db).get_criterion(self.criterion.id).text, "New text")
        self.assertIn("New text", output)

    def test_comment_edit_rewrites_the_text(self) -> None:
        code, output = self._run(
            ["--json", "comment", "edit", "--comment", str(self.comment.id), "--text", "Fixed"]
        )
        self.assertEqual(code, 0)
        rows = Store(self.db).list_comments("plan", self.plan.id)
        self.assertEqual(rows[0].text, "Fixed")
        self.assertIn("Fixed", output)

    def test_comment_edit_requires_text_and_id(self) -> None:
        code, _ = self._run(["comment", "edit", "--comment", str(self.comment.id)])
        self.assertEqual(code, 2)
        code, _ = self._run(["comment", "edit", "--text", "Missing id"])
        self.assertEqual(code, 2)

    def test_json_payloads_parse(self) -> None:
        code, output = self._run(
            ["--json", "criterion", "edit", "--id", str(self.criterion.id), "--text", "Parsed"]
        )
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output)["criteria"]["text"], "Parsed")


if __name__ == "__main__":
    unittest.main()
