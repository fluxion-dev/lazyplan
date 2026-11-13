"""CLI coverage for plan worktree setup output."""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from lazyplan.core.policies.worktrees import derive_worktree
from lazyplan.presentation.cli.main import main as lpui_main
from lazyplan.store import Store


def git(cwd: str, *args: str) -> None:
    subprocess.run(
        ["git", "-C", cwd, *args],
        check=True,
        capture_output=True,
        text=True,
    )


def make_repo(path: str) -> None:
    os.makedirs(path)
    git(path, "init")
    git(path, "config", "user.email", "test@example.test")
    git(path, "config", "user.name", "Test")
    git(path, "config", "commit.gpgsign", "false")
    with open(os.path.join(path, "README.md"), "w", encoding="utf-8") as handle:
        handle.write("readme\n")
    git(path, "add", "README.md")
    git(path, "commit", "-m", "init")
    git(path, "branch", "-M", "main")


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

    def test_duplicate_links_to_one_checkout_print_once(self) -> None:
        store = Store(self.db)
        store.add_repo_link("plan", self.plan.id, self.repo)
        store.add_repo_link("plan", self.plan.id, self.repo, "https://example.com/repo.git")

        code, output, _ = self._run(
            ["--json", "plan", "worktree", "--id", str(self.plan.id), "--print"]
        )

        self.assertEqual(code, 0)
        entries = json.loads(output)["worktrees"]
        self.assertEqual([item["repo_path"] for item in entries], [self.repo])

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


class PlanWorktreeRegisterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = os.path.realpath(self.tmp.name)
        self.db = os.path.join(self.root, "register.db")
        self.repo = os.path.join(self.root, "repo")
        make_repo(self.repo)
        self.env = {"LAZYPLAN_NO_SETUP": "1", "LAZYPLAN_NO_UPDATE_CHECK": "1"}
        self.saved = {key: os.environ.get(key) for key in self.env}
        os.environ.update(self.env)
        self.old_cwd = os.getcwd()

        store = Store(self.db)
        self.plan = store.add_plan("Run every plan", "What", goal="Why")
        store.add_repo_link("plan", self.plan.id, self.repo)
        self.target = derive_worktree(self.repo, self.plan.id, self.plan.name)
        git(
            self.repo,
            "worktree",
            "add",
            "-b",
            self.target.branch,
            self.target.worktree_path,
        )

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

    def test_register_validates_and_records_the_actor(self) -> None:
        code, output, _ = self._run(
            [
                "--json",
                "plan",
                "worktree",
                "add",
                "--id",
                str(self.plan.id),
                "--repo",
                self.repo,
            ]
        )

        self.assertEqual(code, 0)
        row = Store(self.db).get_plan_worktree(self.plan.id, self.repo)
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row.branch, self.target.branch)
        self.assertEqual(row.worktree_path, self.target.worktree_path)
        self.assertEqual(json.loads(output)["worktree"]["branch"], self.target.branch)

    def test_plan_start_requires_registration(self) -> None:
        code, _, error = self._run(["plan", "move", "--id", str(self.plan.id), "--to", "doing"])
        self.assertEqual(code, 2)
        self.assertIn("requires a registered worktree", error)

        code, _, error = self._run(
            ["plan", "move", "--id", str(self.plan.id), "--to", "doing", "--force"]
        )
        self.assertEqual(code, 2)
        self.assertIn("--force needs --reason", error)

        code, _, _ = self._run(
            [
                "plan",
                "move",
                "--id",
                str(self.plan.id),
                "--to",
                "doing",
                "--force",
                "--reason",
                "temporary pairing",
            ]
        )
        self.assertEqual(code, 0)
        self.assertEqual(Store(self.db).get_plan(self.plan.id).status.value, "doing")
        notes = Store(self.db).list_notes("plan", self.plan.id)
        self.assertTrue(any("Worktree gate override" in note.text for note in notes))

    def test_registered_plan_starts(self) -> None:
        self.assertEqual(
            self._run(
                [
                    "plan",
                    "worktree",
                    "add",
                    "--id",
                    str(self.plan.id),
                    "--repo",
                    self.repo,
                ]
            )[0],
            0,
        )

        code, _, error = self._run(["plan", "move", "--id", str(self.plan.id), "--to", "doing"])

        self.assertEqual(code, 0, error)
        self.assertEqual(Store(self.db).get_plan(self.plan.id).status.value, "doing")

    def test_grandfathered_plan_starts_without_a_worktree(self) -> None:
        old = Store(self.db).add_plan("Old", worktree_required=False)

        code, _, error = self._run(["plan", "move", "--id", str(old.id), "--to", "doing"])

        self.assertEqual(code, 0, error)

    def _register_and_task(self) -> int:
        self.assertEqual(
            self._run(
                [
                    "plan",
                    "worktree",
                    "add",
                    "--id",
                    str(self.plan.id),
                    "--repo",
                    self.repo,
                ]
            )[0],
            0,
        )
        store = Store(self.db)
        milestone = store.add_milestone(self.plan.id, "M")
        task = store.add_task(milestone.id, "T", "Approach: x.\n\nCommit: one.\n\nVerify: y.")
        return task.id

    def test_done_refuses_a_dirty_worktree_and_prints_removal(self) -> None:
        self.assertEqual(
            self._run(
                [
                    "plan",
                    "worktree",
                    "add",
                    "--id",
                    str(self.plan.id),
                    "--repo",
                    self.repo,
                ]
            )[0],
            0,
        )
        scratch = os.path.join(self.target.worktree_path, "scratch.txt")
        with open(scratch, "w", encoding="utf-8") as handle:
            handle.write("dirty\n")

        code, _, error = self._run(["plan", "move", "--id", str(self.plan.id), "--to", "done"])
        self.assertEqual(code, 2)
        self.assertIn("uncommitted changes", error)
        self.assertEqual(Store(self.db).get_plan(self.plan.id).status.value, "todo")

        os.remove(scratch)
        code, _, error = self._run(["plan", "move", "--id", str(self.plan.id), "--to", "done"])
        self.assertEqual(code, 0, error)
        self.assertIn("worktree remove", error)
        self.assertEqual(Store(self.db).get_plan(self.plan.id).status.value, "done")

    def test_next_refuses_the_shared_checkout(self) -> None:
        self._register_and_task()
        os.chdir(self.repo)

        code, _, error = self._run(["--actor", "fixture", "next", "--plan", str(self.plan.id)])
        self.assertEqual(code, 2)
        self.assertIn("registered worktree", error)

        code, _, error = self._run(
            [
                "--actor",
                "fixture",
                "next",
                "--plan",
                str(self.plan.id),
                "--force",
                "--reason",
                "temporary pairing",
            ]
        )
        self.assertEqual(code, 0, error)

    def test_claim_refuses_the_shared_checkout(self) -> None:
        task_id = self._register_and_task()
        os.chdir(self.repo)

        code, _, error = self._run(["--actor", "fixture", "claim", "--id", str(task_id)])
        self.assertEqual(code, 2)
        self.assertIn("registered worktree", error)

        code, _, error = self._run(
            [
                "--actor",
                "fixture",
                "claim",
                "--id",
                str(task_id),
                "--force",
                "--reason",
                "temporary pairing",
            ]
        )
        self.assertEqual(code, 0, error)

    def test_claim_succeeds_inside_the_worktree(self) -> None:
        task_id = self._register_and_task()
        os.chdir(self.target.worktree_path)

        code, _, error = self._run(["--actor", "fixture", "claim", "--id", str(task_id)])

        self.assertEqual(code, 0, error)

    def test_session_start_requires_the_registered_worktree(self) -> None:
        self.assertEqual(
            self._run(
                [
                    "plan",
                    "worktree",
                    "add",
                    "--id",
                    str(self.plan.id),
                    "--repo",
                    self.repo,
                ]
            )[0],
            0,
        )
        os.chdir(self.repo)

        code, _, error = self._run(
            ["--actor", "fixture", "session", "start", "--plan", str(self.plan.id)]
        )
        self.assertEqual(code, 2)
        self.assertIn("registered worktree", error)

        code, _, error = self._run(
            ["--actor", "fixture", "session", "start", "--plan", str(self.plan.id), "--force"]
        )
        self.assertEqual(code, 2)
        self.assertIn("--force needs --reason", error)

        code, _, error = self._run(
            [
                "--actor",
                "fixture",
                "session",
                "start",
                "--plan",
                str(self.plan.id),
                "--force",
                "--reason",
                "temporary pairing",
            ]
        )
        self.assertEqual(code, 0, error)

    def test_session_start_succeeds_inside_the_worktree(self) -> None:
        self.assertEqual(
            self._run(
                [
                    "plan",
                    "worktree",
                    "add",
                    "--id",
                    str(self.plan.id),
                    "--repo",
                    self.repo,
                ]
            )[0],
            0,
        )
        os.chdir(self.target.worktree_path)

        code, output, error = self._run(
            ["--actor", "fixture", "--json", "session", "start", "--plan", str(self.plan.id)]
        )

        self.assertEqual(code, 0, error)
        self.assertEqual(json.loads(output)["session"]["plan_id"], self.plan.id)

    def test_deleted_worktree_is_listed_stale_and_kept(self) -> None:
        self.assertEqual(
            self._run(
                [
                    "plan",
                    "worktree",
                    "add",
                    "--id",
                    str(self.plan.id),
                    "--repo",
                    self.repo,
                ]
            )[0],
            0,
        )
        shutil.rmtree(self.target.worktree_path)

        code, output, _ = self._run(
            [
                "--json",
                "plan",
                "worktree",
                "list",
                "--id",
                str(self.plan.id),
                "--stale",
            ]
        )
        self.assertEqual(code, 0)
        entries = json.loads(output)["worktrees"]
        self.assertEqual(len(entries), 1)
        self.assertTrue(entries[0]["stale"])

        code, output, _ = self._run(
            ["--json", "plan", "worktree", "list", "--id", str(self.plan.id)]
        )
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(output)["worktrees"][0]["stale"])
        self.assertIsNotNone(Store(self.db).get_plan_worktree(self.plan.id, self.repo))

    def test_plan_ready_reports_the_worktree_gate(self) -> None:
        code, output, error = self._run(["plan", "ready", "--id", str(self.plan.id)])
        self.assertEqual(code, 1, output + error)
        self.assertIn("worktrees", output)

        self.assertEqual(
            self._run(
                [
                    "plan",
                    "worktree",
                    "add",
                    "--id",
                    str(self.plan.id),
                    "--repo",
                    self.repo,
                ]
            )[0],
            0,
        )
        code, output, error = self._run(["plan", "ready", "--id", str(self.plan.id)])
        self.assertEqual(code, 0, output + error)

    def test_plan_show_and_list_expose_worktrees(self) -> None:
        self.assertEqual(
            self._run(
                [
                    "plan",
                    "worktree",
                    "add",
                    "--id",
                    str(self.plan.id),
                    "--repo",
                    self.repo,
                ]
            )[0],
            0,
        )

        code, output, _ = self._run(["--json", "plan", "show", "--id", str(self.plan.id)])
        self.assertEqual(code, 0)
        row = json.loads(output)["worktrees"][0]
        self.assertEqual(row["branch"], self.target.branch)
        self.assertEqual(row["worktree_path"], self.target.worktree_path)

        code, output, _ = self._run(["plan", "show", "--id", str(self.plan.id)])
        self.assertEqual(code, 0)
        self.assertIn("worktrees (isolation required)", output)
        self.assertIn(self.target.branch, output)
        self.assertIn(self.target.worktree_path, output)

        code, output, _ = self._run(["--json", "list", "--all"])
        self.assertEqual(code, 0)
        entry = next(item for item in json.loads(output) if item["plan"]["id"] == self.plan.id)
        self.assertEqual(entry["worktrees"][0]["branch"], self.target.branch)

    def test_plan_show_porcelain_adds_a_worktree_row(self) -> None:
        self.assertEqual(
            self._run(
                [
                    "plan",
                    "worktree",
                    "add",
                    "--id",
                    str(self.plan.id),
                    "--repo",
                    self.repo,
                ]
            )[0],
            0,
        )

        code, output, _ = self._run(["--porcelain", "plan", "show", "--id", str(self.plan.id)])

        self.assertEqual(code, 0)
        rows = [line for line in output.splitlines() if line.startswith("worktree\t")]
        self.assertEqual(len(rows), 1)
        self.assertIn(self.target.branch, rows[0])

    def test_reregister_is_a_no_op(self) -> None:
        argv = [
            "plan",
            "worktree",
            "add",
            "--id",
            str(self.plan.id),
            "--repo",
            self.repo,
        ]
        self.assertEqual(self._run(argv)[0], 0)
        before = len(Store(self.db).events_by_action("register"))

        code, output, _ = self._run(argv)

        self.assertEqual(code, 0)
        self.assertIn("already-registered", output)
        self.assertEqual(len(Store(self.db).list_plan_worktrees(self.plan.id)), 1)
        self.assertEqual(len(Store(self.db).events_by_action("register")), before)

    def test_remove_unregisters_a_clean_worktree(self) -> None:
        self.assertEqual(
            self._run(
                [
                    "plan",
                    "worktree",
                    "add",
                    "--id",
                    str(self.plan.id),
                    "--repo",
                    self.repo,
                ]
            )[0],
            0,
        )

        code, output, _ = self._run(
            ["plan", "worktree", "remove", "--id", str(self.plan.id), "--repo", self.repo]
        )

        self.assertEqual(code, 0)
        self.assertIn("removed", output)
        self.assertIsNone(Store(self.db).get_plan_worktree(self.plan.id, self.repo))

    def test_remove_refuses_a_dirty_worktree(self) -> None:
        self.assertEqual(
            self._run(
                [
                    "plan",
                    "worktree",
                    "add",
                    "--id",
                    str(self.plan.id),
                    "--repo",
                    self.repo,
                ]
            )[0],
            0,
        )
        with open(
            os.path.join(self.target.worktree_path, "scratch.txt"), "w", encoding="utf-8"
        ) as handle:
            handle.write("dirty\n")

        code, _, error = self._run(
            ["plan", "worktree", "remove", "--id", str(self.plan.id), "--repo", self.repo]
        )

        self.assertEqual(code, 2)
        self.assertIn("uncommitted changes", error)
        self.assertIsNotNone(Store(self.db).get_plan_worktree(self.plan.id, self.repo))

    def test_remove_unknown_registration_is_an_error(self) -> None:
        code, _, error = self._run(
            ["plan", "worktree", "remove", "--id", str(self.plan.id), "--repo", self.repo]
        )
        self.assertEqual(code, 1)
        self.assertIn("has no worktree", error)

    def test_add_refuses_an_unlinked_repo(self) -> None:
        other = os.path.join(self.root, "other")
        make_repo(other)

        code, _, error = self._run(
            [
                "plan",
                "worktree",
                "add",
                "--id",
                str(self.plan.id),
                "--repo",
                other,
            ]
        )

        self.assertEqual(code, 2)
        self.assertIn("not linked", error)
