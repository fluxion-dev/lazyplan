"""Touch-point CLI and claim location fields."""

from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from lazyplan.presentation.cli import main as lpui_main
from lazyplan.store import Store


class TouchCliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "t.db")
        self.store = Store(self.db)
        plan = self.store.add_plan("P", worktree_required=False)
        milestone = self.store.add_milestone(plan.id, "M")
        self.task = self.store.add_task(milestone.id, "T")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _run(self, *argv: str) -> tuple[int, str, str]:
        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = lpui_main(["--db", self.db, *argv])
        return code, out.getvalue(), err.getvalue()

    def test_add_list_remove(self) -> None:
        code, out, err = self._run(
            "--json", "touch", "add", "--task", str(self.task.id), "--path", "./src/store/"
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["touchpoints"], ["src/store"])
        code, out, err = self._run("--json", "touch", "list", "--task", str(self.task.id))
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["touchpoints"], ["src/store"])
        code, out, err = self._run("touch", "list", "--task", str(self.task.id))
        self.assertIn("src/store", out)
        code, _out, err = self._run(
            "touch", "remove", "--task", str(self.task.id), "--path", "src/store"
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(self.store.list_touchpoints(self.task.id), [])

    def test_invalid_path_and_missing_task(self) -> None:
        code, _out, err = self._run(
            "touch", "add", "--task", str(self.task.id), "--path", "../outside"
        )
        self.assertEqual(code, 2)
        self.assertIn("escape", err)
        code, _out, err = self._run("touch", "list", "--task", "999")
        self.assertEqual(code, 1)

    def test_task_add_writes_touchpoints_in_one_transaction(self) -> None:
        code, out, err = self._run(
            "--json",
            "task",
            "add",
            "--milestone",
            "1",
            "--title",
            "New task",
            "--touch",
            "src/store",
            "--touch",
            "src/tui",
        )
        self.assertEqual(code, 0, err)
        task_id = json.loads(out)["task"]["id"]
        self.assertEqual(self.store.list_touchpoints(task_id), ["src/store", "src/tui"])
        code, _out, err = self._run(
            "task", "add", "--milestone", "1", "--title", "Bad", "--touch", "../outside"
        )
        self.assertEqual(code, 2)
        self.assertIsNone(
            next(
                (task for task in self.store.list_tasks(1) if task.title == "Bad"),
                None,
            )
        )

    def test_claim_records_locations(self) -> None:
        code, out, err = self._run(
            "--json",
            "claim",
            "--id",
            str(self.task.id),
            "--worktree",
            "/repo/wt",
            "--repo",
            "/repo",
        )
        self.assertEqual(code, 0, err)
        claim = json.loads(out)["claim"]
        self.assertEqual(claim["worktree"], "/repo/wt")
        self.assertEqual(claim["repo_path"], "/repo")


if __name__ == "__main__":
    unittest.main()
