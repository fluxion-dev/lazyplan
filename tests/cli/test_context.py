"""Context CLI: read-only packet, budget errors, and porcelain rows."""

from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from lazyplan import services
from lazyplan.core.entities import Status
from lazyplan.presentation import setup
from lazyplan.presentation.cli import main as lpui_main
from lazyplan.store import Store
from tests.support.home import sandbox_home


class ContextCliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        self.home.mkdir()
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir()
        self.old_cwd = os.getcwd()
        self.old_db = os.environ.pop("LAZYPLAN_DB", None)
        self.old_nosetup = os.environ.pop(setup.NO_SETUP_ENV, None)
        sandbox_home(self, str(self.home))
        os.chdir(self.repo)

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

    def _run(self, *argv: str) -> tuple[int, str, str]:
        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = lpui_main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def _seed(self) -> tuple[int, int]:
        store = Store(self.home / ".lazyplan/lazyplan.db")
        plan = store.add_plan("P", "what", goal="why")
        milestone = store.add_milestone(plan.id, "M", "desc")
        doing = store.add_task(milestone.id, "Doing task", "desc")
        store.add_task(milestone.id, "Next task", "desc")
        services.set_status(store, "task", doing.id, Status.DOING, actor="t")
        services.set_status(store, "milestone", milestone.id, Status.DOING, actor="t")
        services.set_status(store, "plan", plan.id, Status.DOING, actor="t")
        store.claim_task(doing.id, "alice", 300)
        return plan.id, doing.id

    def test_missing_database_is_empty_and_file_free(self):
        code, out, err = self._run("--json", "context")
        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertEqual(payload["active"], 0)
        self.assertFalse((self.home / ".lazyplan").exists())

    def test_json_reports_the_active_packet(self):
        plan_id, task_id = self._seed()
        code, out, err = self._run("--json", "context")
        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertEqual(payload["plans"][0]["id"], plan_id)
        self.assertEqual(payload["plans"][0]["doing"][0]["id"], task_id)

    def test_small_budget_is_an_error(self):
        self._seed()
        code, _out, err = self._run("--json", "context", "--max-chars", "100")
        self.assertEqual(code, 2)
        self.assertIn("max_chars", err)

    def test_missing_plan_is_an_error(self):
        self._seed()
        code, _out, err = self._run("--json", "context", "--plan", "999")
        self.assertEqual(code, 1)
        self.assertIn("not found", err)

    def test_porcelain_rows(self):
        self._seed()
        code, out, err = self._run("--porcelain", "context")
        self.assertEqual(code, 0, err)
        self.assertTrue(out.startswith("metric\tactive\t"))
        self.assertIn("plan\t", out)
        self.assertIn("task\t", out)

    def test_text_names_the_doing_task(self):
        self._seed()
        code, out, err = self._run("context")
        self.assertEqual(code, 0, err)
        self.assertIn("Doing task", out)
        self.assertIn("Next task", out)


if __name__ == "__main__":
    unittest.main()
