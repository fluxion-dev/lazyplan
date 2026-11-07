"""External reference CLI: link, list, and unlink."""

from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from lazyplan.presentation.cli import main as lpui_main
from lazyplan.store import Store


class RefCliTest(unittest.TestCase):
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

    def test_link_list_unlink(self) -> None:
        code, out, err = self._run(
            "--json",
            "ref",
            "link",
            "--plan",
            str(self.plan.id),
            "--url",
            "https://github.com/o/r/issues/7",
            "--title",
            "Epic",
        )
        self.assertEqual(code, 0, err)
        ref = json.loads(out)["ref"]
        self.assertEqual(ref["provider"], "github")
        self.assertEqual(ref["external_id"], "7")
        code, out, err = self._run("--json", "ref", "list", "--plan", str(self.plan.id))
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)[0]["id"], ref["id"])
        code, out, err = self._run("ref", "list", "--plan", str(self.plan.id))
        self.assertIn("github/issue", out)
        code, _out, err = self._run(
            "ref", "unlink", "--plan", str(self.plan.id), "--id", str(ref["id"])
        )
        self.assertEqual(code, 0, err)

    def test_link_is_idempotent(self) -> None:
        args = (
            "ref",
            "link",
            "--plan",
            str(self.plan.id),
            "--url",
            "https://example.com/a",
            "--title",
            "A",
        )
        self.assertEqual(self._run(*args)[0], 0)
        self.assertEqual(self._run(*args)[0], 0)
        self.assertEqual(len(self.store.list_refs(self.plan.id)), 1)

    def test_invalid_url_and_missing_plan(self) -> None:
        code, _out, err = self._run(
            "ref", "link", "--plan", str(self.plan.id), "--url", "ftp://example.com"
        )
        self.assertEqual(code, 2)
        self.assertIn("http", err)
        code, _out, err = self._run("ref", "list", "--plan", "999")
        self.assertEqual(code, 1)

    def test_unlink_requires_an_identifier(self) -> None:
        code, _out, err = self._run("ref", "unlink", "--plan", str(self.plan.id))
        self.assertEqual(code, 2)
        self.assertIn("--id or --url", err)

    def test_list_without_database_does_not_create_one(self) -> None:
        missing = os.path.join(self.tmp.name, "missing.db")
        out = io.StringIO()
        with redirect_stdout(out):
            code = lpui_main(["--db", missing, "ref", "list", "--plan", "1"])
        self.assertEqual(code, 0)
        self.assertIn("no database", out.getvalue())
        self.assertFalse(os.path.exists(missing))


if __name__ == "__main__":
    unittest.main()
