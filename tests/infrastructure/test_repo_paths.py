"""Repo path normalization shared by links, claims, and VCS comparisons."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from lazyplan.infrastructure.repo import git_common_dir
from lazyplan.infrastructure.repo_paths import normalize_repo_path, resolve_repo_path


class TestRepoPaths(unittest.TestCase):
    def test_empty_path_stays_empty(self) -> None:
        self.assertEqual(resolve_repo_path(""), "")
        self.assertEqual(normalize_repo_path(""), "")

    def test_equivalent_paths_resolve_alike(self) -> None:
        self.assertEqual(resolve_repo_path("/repo/."), resolve_repo_path("/repo"))
        self.assertEqual(resolve_repo_path("/repo/../repo"), resolve_repo_path("/repo"))

    def test_normalized_paths_compare_alike(self) -> None:
        self.assertEqual(normalize_repo_path("/repo/."), normalize_repo_path("/repo"))

    def test_linked_worktrees_share_a_project_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "root"
            root.mkdir()
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(
                ["git", "-C", str(root), "config", "user.email", "a@example.com"], check=True
            )
            subprocess.run(["git", "-C", str(root), "config", "user.name", "A"], check=True)
            (root / "file.txt").write_text("x", encoding="utf-8")
            subprocess.run(["git", "-C", str(root), "add", "."], check=True)
            subprocess.run(["git", "-C", str(root), "commit", "-qm", "init"], check=True)
            linked = Path(tmp) / "linked"
            subprocess.run(
                ["git", "-C", str(root), "worktree", "add", "-q", str(linked)],
                check=True,
            )
            self.assertEqual(git_common_dir(root), git_common_dir(linked))
            self.assertTrue(git_common_dir(root))
            self.assertEqual(git_common_dir(Path(tmp)), "")


if __name__ == "__main__":
    unittest.main()
