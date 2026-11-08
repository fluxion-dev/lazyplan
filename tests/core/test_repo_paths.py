"""Repo path normalization shared by links, claims, and VCS comparisons."""

from __future__ import annotations

import unittest

from lazyplan.core.policies.repo_paths import normalize_repo_path, resolve_repo_path


class TestRepoPaths(unittest.TestCase):
    def test_empty_path_stays_empty(self) -> None:
        self.assertEqual(resolve_repo_path(""), "")
        self.assertEqual(normalize_repo_path(""), "")

    def test_equivalent_paths_resolve_alike(self) -> None:
        self.assertEqual(resolve_repo_path("/repo/."), resolve_repo_path("/repo"))
        self.assertEqual(resolve_repo_path("/repo/../repo"), resolve_repo_path("/repo"))

    def test_normalized_paths_compare_alike(self) -> None:
        self.assertEqual(normalize_repo_path("/repo/."), normalize_repo_path("/repo"))


if __name__ == "__main__":
    unittest.main()
