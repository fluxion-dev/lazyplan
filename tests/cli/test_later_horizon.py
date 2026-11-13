"""Later horizon CLI walkthrough: touch, claim, ref, and ship."""

from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from lazyplan.presentation.cli import main as lpui_main
from lazyplan.store import Store


class TestLaterHorizonCli(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "later.db")
        self.store = Store(self.db)
        plan = self.store.add_plan("Later", worktree_required=False)
        checkout = self.store.checkout_path()
        self.store.register_plan_worktree(plan.id, checkout, checkout)
        milestone = self.store.add_milestone(plan.id, "M")
        self.first = self.store.add_task(milestone.id, "First")
        self.second = self.store.add_task(milestone.id, "Second")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _run(self, *argv: str) -> tuple[int, str, str]:
        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = lpui_main(["--db", self.db, "--actor", "ana", *argv])
        return code, out.getvalue(), err.getvalue()

    def test_walkthrough(self) -> None:
        code, _out, err = self._run(
            "touch", "add", "--task", str(self.first.id), "--path", "src/store"
        )
        self.assertEqual(code, 0, err)
        self._run("touch", "add", "--task", str(self.second.id), "--path", "src/store/base.py")
        code, out, err = self._run("--json", "claim", "--id", str(self.first.id), "--repo", "/repo")
        self.assertEqual(code, 0, err)
        code, _out, err = self._run("claim", "--id", str(self.second.id), "--repo", "/repo")
        self.assertEqual(code, 1)
        code, out, err = self._run(
            "--json", "ref", "link", "--plan", "1", "--url", "https://example.com/a"
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["ref"]["provider"], "other")
        code, out, err = self._run("ship", "--plan", "1")
        self.assertEqual(code, 0, err)
        self.assertIn("## Follow-ups", out)


if __name__ == "__main__":
    unittest.main()
