"""CLI coverage for plan worktree setup output."""

from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from lazyplan.presentation.cli.main import main as lpui_main
from lazyplan.store import Store


class PlanWorktreeCommandTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = os.path.realpath(self.tmp.name)
        self.db = os.path.join(self.root, "worktree.db")
        self.repo = os.path.join(self.root, "repo")
        os.makedirs(os.path.join(self.repo, ".git"))
        self.env = {"LAZYPLAN_NO_SETUP": "1", "LAZYPLAN_NO_UPDATE_CHECK": "1"}
        self.saved = {key: os.environ.get(key) for key in self.env}
        os.environ.update(self.env)
        self.old_cwd = os.getcwd()
        store = Store(self.db)
        self.plan = store.add_plan("Run every plan", "What", goal="Why")

    def tearDown(self) -> None:
        os.chdir(self.old_cwd)
        for key, value in self.saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()

    def _run(self, argv: list[str]) -> tuple[int, str, str]:
        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = lpui_main(["--db", self.db, *argv])
        return code, out.getvalue(), err.getvalue()

    def _target(self) -> dict:
        return {
            "repo_path": self.repo,
            "worktree_path": os.path.join(self.root, f"repo--plan-{self.plan.id}-run-every-plan"),
            "branch": f"plan/{self.plan.id}-run-every-plan",
        }

    def test_prints_one_command_for_a_linked_repo(self) -> None:
        Store(self.db).add_repo_link("plan", self.plan.id, self.repo)

        code, output, _ = self._run(
            ["--json", "plan", "worktree", "--id", str(self.plan.id), "--print"]
        )

        self.assertEqual(code, 0)
        data = json.loads(output)
        self.assertEqual(len(data["worktrees"]), 1)
        entry = data["worktrees"][0]
        target = self._target()
        self.assertEqual(entry["repo_path"], target["repo_path"])
        self.assertEqual(entry["worktree_path"], target["worktree_path"])
        self.assertEqual(entry["branch"], target["branch"])
        self.assertIn("git -C", entry["command"])
        self.assertIn("worktree add -b", entry["command"])

    def test_prints_one_command_per_linked_repo(self) -> None:
        other = os.path.join(self.root, "site")
        os.makedirs(os.path.join(other, ".git"))
        store = Store(self.db)
        store.add_repo_link("plan", self.plan.id, self.repo)
        store.add_repo_link("plan", self.plan.id, other)

        code, output, _ = self._run(
            ["--json", "plan", "worktree", "--id", str(self.plan.id), "--print"]
        )

        self.assertEqual(code, 0)
        entries = json.loads(output)["worktrees"]
        self.assertEqual([item["repo_path"] for item in entries], [self.repo, other])
        self.assertEqual({item["branch"] for item in entries}, {self._target()["branch"]})

    def test_missing_links_default_to_the_current_checkout(self) -> None:
        os.chdir(self.repo)

        code, output, _ = self._run(
            ["--json", "plan", "worktree", "--id", str(self.plan.id), "--print"]
        )

        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output)["worktrees"][0]["repo_path"], self.repo)
        self.assertEqual(Store(self.db).list_repos("plan", self.plan.id)[0]["repo_path"], self.repo)

    def test_existing_path_is_refused(self) -> None:
        Store(self.db).add_repo_link("plan", self.plan.id, self.repo)
        os.makedirs(self._target()["worktree_path"])

        code, _, error = self._run(["plan", "worktree", "--id", str(self.plan.id), "--print"])

        self.assertEqual(code, 2)
        self.assertIn("already exists", error)

    def test_human_output_labels_each_command(self) -> None:
        Store(self.db).add_repo_link("plan", self.plan.id, self.repo)

        code, output, _ = self._run(["plan", "worktree", "--id", str(self.plan.id), "--print"])

        self.assertEqual(code, 0)
        self.assertIn(f"repo {self.repo}", output)
        self.assertIn("git -C", output)
