"""Question CLI: add, list, resolve, and reopen."""

from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from lazyplan.presentation.cli import main as lpui_main
from lazyplan.store import Store


class QuestionCliTest(unittest.TestCase):
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

    def _add(self, text: str = "Which host?") -> tuple[int, str, str]:
        return self._run("--json", "question", "add", "--plan", str(self.plan.id), "--text", text)

    def test_add_list_resolve_reopen(self) -> None:
        code, out, err = self._add()
        self.assertEqual(code, 0, err)
        question = json.loads(out)["question"]
        self.assertEqual(question["status"], "open")

        code, out, err = self._run("--json", "question", "list", "--plan", str(self.plan.id))
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)[0]["id"], question["id"])

        code, out, err = self._run(
            "--json",
            "question",
            "resolve",
            "--id",
            str(question["id"]),
            "--note",
            "OpenCode first",
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["question"]["resolution"], "OpenCode first")
        code, out, _err = self._run("--json", "question", "list", "--plan", str(self.plan.id))
        self.assertEqual(json.loads(out), [])
        code, out, _err = self._run(
            "--json", "question", "list", "--plan", str(self.plan.id), "--status", "all"
        )
        self.assertEqual(len(json.loads(out)), 1)

        code, out, err = self._run(
            "--json",
            "question",
            "reopen",
            "--id",
            str(question["id"]),
            "--note",
            "changed",
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["question"]["status"], "open")

    def test_text_and_porcelain(self) -> None:
        self._add()
        code, out, err = self._run("question", "list", "--plan", str(self.plan.id))
        self.assertEqual(code, 0, err)
        self.assertIn("Q1 [open] Which host?", out)
        code, out, err = self._run("--porcelain", "question", "list", "--plan", str(self.plan.id))
        self.assertEqual(code, 0, err)
        self.assertEqual(out.split("\t")[0], "question")

    def test_duplicate_and_unknown_plan(self) -> None:
        self._add()
        code, _out, err = self._add()
        self.assertEqual(code, 2)
        self.assertIn("already open", err)
        code, _out, err = self._run("question", "add", "--plan", "999", "--text", "Why?")
        self.assertEqual(code, 1)

    def test_list_without_database_does_not_create_one(self) -> None:
        missing = os.path.join(self.tmp.name, "missing.db")
        out = io.StringIO()
        with redirect_stdout(out):
            code = lpui_main(["--db", missing, "question", "list", "--plan", "1"])
        self.assertEqual(code, 0)
        self.assertIn("no database", out.getvalue())
        self.assertFalse(os.path.exists(missing))


if __name__ == "__main__":
    unittest.main()
