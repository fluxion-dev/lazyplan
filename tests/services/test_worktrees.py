"""Plan worktree verification against real git worktrees."""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest

from lazyplan.services.worktrees import verify_worktree


def git(cwd: str, *args: str) -> None:
    subprocess.run(
        ["git", "-C", cwd, *args],
        check=True,
        capture_output=True,
        text=True,
    )


def make_repo(root: str) -> str:
    repo = os.path.join(root, "main")
    os.makedirs(repo)
    git(repo, "init")
    git(repo, "config", "user.email", "test@example.test")
    git(repo, "config", "user.name", "Test")
    git(repo, "config", "commit.gpgsign", "false")
    with open(os.path.join(repo, "README.md"), "w", encoding="utf-8") as handle:
        handle.write("readme\n")
    git(repo, "add", "README.md")
    git(repo, "commit", "-m", "init")
    git(repo, "branch", "-M", "main")
    return repo


class TestVerifyWorktree(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = os.path.realpath(self.tmp.name)
        self.repo = make_repo(self.root)
        self.worktree = os.path.join(self.root, "main--plan-6-test")
        git(self.repo, "worktree", "add", "-b", "plan/6-test", self.worktree)

    def tearDown(self):
        self.tmp.cleanup()

    def test_clean_worktree_on_the_expected_branch(self):
        result = verify_worktree(self.repo, self.worktree, "plan/6-test")

        self.assertTrue(result.ok, result.reason)
        self.assertEqual(result.branch, "plan/6-test")
        self.assertTrue(result.head)
        self.assertFalse(result.dirty)

    def test_dirty_worktree_is_refused(self):
        with open(os.path.join(self.worktree, "scratch.txt"), "w", encoding="utf-8") as handle:
            handle.write("work in progress\n")

        result = verify_worktree(self.repo, self.worktree, "plan/6-test")

        self.assertFalse(result.ok)
        self.assertIn("uncommitted changes", result.reason)
        self.assertTrue(result.dirty)

    def test_wrong_branch_is_refused(self):
        other = os.path.join(self.root, "main--plan-6-other")
        git(self.repo, "worktree", "add", "-b", "plan/6-other", other)

        result = verify_worktree(self.repo, other, "plan/6-test")

        self.assertFalse(result.ok)
        self.assertIn("plan/6-other", result.reason)
        self.assertIn("plan/6-test", result.reason)

    def test_other_repository_is_refused(self):
        other_root = os.path.join(self.root, "second")
        os.makedirs(other_root)
        other_repo = make_repo(other_root)
        other_worktree = os.path.join(other_root, "main--plan-6-test")
        git(other_repo, "worktree", "add", "-b", "plan/6-test", other_worktree)

        result = verify_worktree(self.repo, other_worktree, "plan/6-test")

        self.assertFalse(result.ok)
        self.assertIn("different repository", result.reason)

    def test_missing_worktree_and_non_git_repo_are_refused(self):
        missing = verify_worktree(self.repo, os.path.join(self.root, "missing"), "plan/6-test")
        self.assertFalse(missing.ok)
        self.assertIn("not a git checkout", missing.reason)

        plain = os.path.join(self.root, "plain")
        os.makedirs(plain)
        result = verify_worktree(plain, self.worktree, "plan/6-test")
        self.assertFalse(result.ok)
        self.assertIn("linked checkout is not a git repository", result.reason)

    def test_worktree_must_differ_from_the_checkout(self):
        result = verify_worktree(self.repo, self.repo, "main")
        self.assertFalse(result.ok)
        self.assertIn("must differ", result.reason)
