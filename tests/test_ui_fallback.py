"""`lpui` without a TTY prints a readable summary, never the full-screen UI."""

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from home_sandbox import sandbox_home  # noqa: E402

from lazyplan import setup  # noqa: E402
from lazyplan.cli import main as lpui_main  # noqa: E402
from lazyplan.store import Store  # noqa: E402


class UiFallbackCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        self.home.mkdir()
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir()
        self.old_db = os.environ.pop("LAZYPLAN_DB", None)
        self.old_nosetup = os.environ.pop(setup.NO_SETUP_ENV, None)
        self.old_cwd = os.getcwd()
        sandbox_home(self, str(self.home))
        os.chdir(self.repo)
        store = Store(self.home / ".lazyplan/lazyplan.db")
        plan = store.add_plan("Visible plan", "what", goal="why")
        milestone = store.add_milestone(plan.id, "M", "desc")
        store.add_task(milestone.id, "T", "desc")

    def tearDown(self):
        os.chdir(self.old_cwd)
        for key, value in (
            ("LAZYPLAN_DB", self.old_db),
            (setup.NO_SETUP_ENV, self.old_nosetup),
        ):
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()

    def _run(self, argv: list[str]) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with (
            mock.patch("lazyplan.cli._interactive_terminal", return_value=False),
            redirect_stdout(out),
            redirect_stderr(err),
        ):
            code = lpui_main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_piped_run_prints_newlines_not_ansi(self):
        code, out, err = self._run([])
        self.assertEqual(code, 0)
        self.assertIn("Visible plan", out)
        self.assertIn("\n", out)
        self.assertNotIn("\x1b", out)
        self.assertIn("no interactive terminal", err)

    def test_piped_json_stays_pure(self):
        code, out, err = self._run(["--json"])
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload[0]["plan"]["name"], "Visible plan")
        self.assertNotIn("\x1b", out)
        self.assertNotIn("no interactive terminal", err)

    def test_empty_database_prints_the_empty_line(self):
        with mock.patch("lazyplan.cli._interactive_terminal", return_value=False):
            Store(self.home / ".lazyplan/lazyplan.db")
            # remove the seeded plan tree by using a fresh DB below
        fresh = Path(self.tmp.name) / "fresh.db"
        out = io.StringIO()
        with (
            mock.patch("lazyplan.cli._interactive_terminal", return_value=False),
            redirect_stdout(out),
        ):
            code = lpui_main(["--db", str(fresh)])
        self.assertEqual(code, 0)
        self.assertIn("No plans yet", out.getvalue())


if __name__ == "__main__":
    unittest.main()
