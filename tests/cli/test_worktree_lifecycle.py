"""End-to-end plan worktree lifecycle: grandfather, gate, adopt, close."""

from __future__ import annotations

import io
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from lazyplan.core.policies.worktrees import derive_worktree
from lazyplan.presentation.cli.main import main as lpui_main
from lazyplan.store import Store


def git(cwd: str, *args: str) -> None:
    subprocess.run(["git", "-C", cwd, *args], check=True, capture_output=True, text=True)


class PlanWorktreeLifecycleTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = os.path.realpath(self.tmp.name)
        self.repo = os.path.join(self.root, "repo")
        os.makedirs(self.repo)
        git(self.repo, "init")
        git(self.repo, "config", "user.email", "test@example.test")
        git(self.repo, "config", "user.name", "Test")
        git(self.repo, "config", "commit.gpgsign", "false")
        with open(os.path.join(self.repo, "README.md"), "w", encoding="utf-8") as handle:
            handle.write("readme\n")
        git(self.repo, "add", "README.md")
        git(self.repo, "commit", "-m", "init")
        git(self.repo, "branch", "-M", "main")
        self.db = os.path.join(self.root, "lifecycle.db")
        self.old = Store(self.db).add_plan("Old plan", worktree_required=False)
        self.new = Store(self.db).add_plan("New plan")
        store = Store(self.db)
        store.add_repo_link("plan", self.old.id, self.repo)
        store.add_repo_link("plan", self.new.id, self.repo)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _run(self, *argv: str) -> tuple[int, str, str]:
        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = lpui_main(["--db", self.db, *argv])
        return code, out.getvalue(), err.getvalue()

    def test_grandfather_gate_adopt_and_close(self) -> None:
        code, _, error = self._run("plan", "move", "--id", str(self.old.id), "--to", "doing")
        self.assertEqual(code, 0, error)

        code, _, error = self._run("plan", "move", "--id", str(self.new.id), "--to", "doing")
        self.assertEqual(code, 2)
        self.assertIn("registered worktree", error)

        target = derive_worktree(self.repo, self.new.id, self.new.name)
        git(self.repo, "worktree", "add", "-b", target.branch, target.worktree_path)
        code, _, error = self._run(
            "plan",
            "worktree",
            "add",
            "--id",
            str(self.new.id),
            "--repo",
            self.repo,
        )
        self.assertEqual(code, 0, error)

        code, _, error = self._run("plan", "move", "--id", str(self.new.id), "--to", "doing")
        self.assertEqual(code, 0, error)

        code, _, error = self._run("plan", "move", "--id", str(self.new.id), "--to", "done")
        self.assertEqual(code, 0, error)
        self.assertIn("worktree remove", error)

        git(self.repo, "worktree", "remove", target.worktree_path)
        code, _, error = self._run(
            "plan",
            "worktree",
            "remove",
            "--id",
            str(self.new.id),
            "--repo",
            self.repo,
        )
        self.assertEqual(code, 0, error)
        self.assertIsNone(Store(self.db).get_plan_worktree(self.new.id, self.repo))

        code, output, error = self._run(
            "--json", "plan", "worktree", "list", "--id", str(self.new.id)
        )
        self.assertEqual(code, 0, error)
        self.assertEqual(json.loads(output)["worktrees"], [])


if __name__ == "__main__":
    unittest.main()
