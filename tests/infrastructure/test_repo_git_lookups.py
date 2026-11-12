"""Toplevel and common-dir lookups: one git call per directory inside a hook run."""

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from lazyplan.infrastructure import repo


def _git(*args: str, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


class GitLookupsCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name).resolve()
        cls.top = root / "repo"
        cls.top.mkdir()
        _git("init", "-q", "-b", "main", cwd=cls.top)
        _git(
            "-c",
            "user.email=t@e.st",
            "-c",
            "user.name=t",
            "commit",
            "-q",
            "--allow-empty",
            "-m",
            "init",
            cwd=cls.top,
        )
        cls.sub = cls.top / "sub"
        cls.sub.mkdir()
        cls.linked = root / "linked"
        _git("worktree", "add", "-q", str(cls.linked), cwd=cls.top)
        cls.bare = root / "bare.git"
        _git("init", "-q", "--bare", str(cls.bare), cwd=root)
        cls.plain = root / "plain"
        cls.plain.mkdir()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def _answers(self) -> dict:
        return {
            name: (repo._git_toplevel(path), repo.git_common_dir(path))
            for name, path in (
                ("top", self.top),
                ("sub", self.sub),
                ("linked", self.linked),
                ("bare", self.bare),
                ("plain", self.plain),
            )
        }

    def test_each_kind_of_folder_gets_its_toplevel_and_common_dir(self):
        answers = self._answers()
        common = str((self.top / ".git").resolve())
        self.assertEqual(answers["top"], (self.top, common))
        self.assertEqual(answers["sub"], (self.top, common))
        self.assertEqual(answers["linked"], (self.linked, common))
        self.assertEqual(answers["bare"], (None, str(self.bare.resolve())))
        self.assertEqual(answers["plain"], (None, ""))

    def test_shared_lookups_give_the_same_answers(self):
        separate = self._answers()
        with repo.shared_git_lookups():
            shared = self._answers()
        self.assertEqual(shared, separate)

    def test_one_git_call_answers_a_folder_and_its_toplevel_in_a_hook_run(self):
        with (
            mock.patch.object(repo.subprocess, "run", wraps=subprocess.run) as run,
            repo.shared_git_lookups(),
        ):
            repo.find_repo_root(self.sub)
            repo.git_common_dir(self.sub)
            repo.find_repo_root(self.top)
            repo.git_common_dir(str(self.top))
        self.assertEqual(run.call_count, 1)

    def test_lookups_outside_a_hook_run_ask_git_every_time(self):
        with mock.patch.object(repo.subprocess, "run", wraps=subprocess.run) as run:
            repo.find_repo_root(self.top)
            repo.find_repo_root(self.top)
        self.assertEqual(run.call_count, 2)

    def test_a_missing_git_is_outside_a_checkout(self):
        with mock.patch.object(repo.subprocess, "run", side_effect=FileNotFoundError("git")):
            self.assertIsNone(repo._git_toplevel(self.top))
            self.assertEqual(repo.git_common_dir(self.top), "")


if __name__ == "__main__":
    unittest.main()
