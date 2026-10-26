"""Read-only share: escaped HTML, safe JSON, and file handling."""

from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from home_sandbox import sandbox_home  # noqa: E402

from lazyplan import share  # noqa: E402
from lazyplan.cli import main as lpui_main  # noqa: E402
from lazyplan.store import Store  # noqa: E402


class TestShare(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "share.db")
        store = Store(self.db)
        plan = store.add_plan("P <script>", "what & why", goal="because", actor="fixture")
        milestone = store.add_milestone(plan.id, "M", actor="fixture")
        store.add_task(milestone.id, "T", actor="fixture")
        store.add_criteria("plan", plan.id, "<b>safe</b>", actor="fixture")
        store.add_note("plan", plan.id, "note", actor="fixture")
        store.add_comment("plan", plan.id, "comment <i>", actor="fixture")
        store.link_forge("task", 1, 7, title="PR", payload='{"token":"secret"}', actor="fixture")
        self.store = store
        self.old_setup = os.environ.get("LAZYPLAN_NO_SETUP")
        sandbox_home(self, self.tmp.name)
        os.environ["LAZYPLAN_NO_SETUP"] = "1"

    def tearDown(self):
        for key, value in (("LAZYPLAN_NO_SETUP", self.old_setup),):
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()

    def _run(self, *argv: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = lpui_main(["--db", self.db, "--actor", "qa", *argv])
        return code, out.getvalue(), err.getvalue()

    def test_html_escapes_and_contains_context(self):
        html = share.render_html(self.store, 1)
        assert html is not None
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("&amp;", html)
        self.assertIn("&lt;b&gt;safe&lt;/b&gt;", html)
        self.assertIn("comment &lt;i&gt;", html)
        self.assertIn("because", html)
        self.assertNotIn("secret", html)
        self.assertNotIn("<script>", html)

    def test_json_is_safe(self):
        text = share.render_json(self.store, 1)
        assert text is not None
        data = json.loads(text)
        self.assertEqual(data["plan"]["id"], 1)
        self.assertNotIn("payload", json.dumps(data))
        self.assertNotIn("secret", text)

    def test_cli_stdout_file_and_missing_plan(self):
        code, out, err = self._run("share", "--plan", "1")
        self.assertEqual(code, 0, err)
        self.assertIn("<!doctype html>", out)
        dest = os.path.join(self.tmp.name, "plan.html")
        code, out, err = self._run("share", "--plan", "1", "--out", dest)
        self.assertEqual(code, 0, err)
        self.assertIn("shared P1", out)
        self.assertTrue(os.path.exists(dest))
        code, out, err = self._run("share", "--plan", "99")
        self.assertEqual(code, 1)
        self.assertIn("plan 99", err)


if __name__ == "__main__":
    unittest.main()
