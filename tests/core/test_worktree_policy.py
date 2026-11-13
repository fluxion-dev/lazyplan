"""Plan worktree derivation: slugs, sibling paths, collisions."""

from __future__ import annotations

import os
import unittest

from lazyplan.core.policies.worktrees import (
    WorktreeCollision,
    WorktreeTarget,
    derive_worktree,
    derive_worktrees,
    slugify,
)

ROOT = os.path.join(os.path.abspath(os.sep), "repos")
REPO = os.path.join(ROOT, "lazyplan")


class TestSlugify(unittest.TestCase):
    def test_words_become_lowercase_hyphens(self):
        self.assertEqual(
            slugify("Run every plan in its own worktree"), "run-every-plan-in-its-own-worktree"
        )
        self.assertEqual(slugify("  Hello, World!  "), "hello-world")

    def test_empty_and_symbol_only_titles_fall_back(self):
        self.assertEqual(slugify(""), "plan")
        self.assertEqual(slugify("!!!"), "plan")

    def test_slug_is_bounded_without_a_trailing_hyphen(self):
        slug = slugify("word " * 30)
        self.assertLessEqual(len(slug), 48)
        self.assertFalse(slug.endswith("-"))
        self.assertTrue(slug)


class TestDeriveWorktree(unittest.TestCase):
    def test_derives_a_sibling_path_and_branch(self):
        target = derive_worktree(REPO, 6, "Run every plan")

        self.assertEqual(target.repo_path, REPO)
        self.assertEqual(
            target.worktree_path,
            os.path.join(ROOT, "lazyplan--plan-6-run-every-plan"),
        )
        self.assertEqual(target.branch, "plan/6-run-every-plan")

    def test_normalizes_a_trailing_separator(self):
        target = derive_worktree(REPO + os.sep, 6, "Plan")
        self.assertEqual(target.repo_path, REPO)

    def test_rejects_a_relative_or_bare_path(self):
        for path in ("lazyplan", os.path.join("repos", "lazyplan")):
            with self.subTest(path=path), self.assertRaises(ValueError):
                derive_worktree(path, 6, "Plan")


class TestDeriveWorktrees(unittest.TestCase):
    def test_multi_repo_plans_get_one_target_each(self):
        other = os.path.join(ROOT, "site")
        targets = derive_worktrees([REPO, other], 7, "Agent registry")

        self.assertEqual([item.repo_path for item in targets], [REPO, other])
        self.assertEqual(
            [item.branch for item in targets],
            ["plan/7-agent-registry", "plan/7-agent-registry"],
        )
        self.assertEqual(
            [item.worktree_path for item in targets],
            [
                os.path.join(ROOT, "lazyplan--plan-7-agent-registry"),
                os.path.join(ROOT, "site--plan-7-agent-registry"),
            ],
        )

    def test_duplicate_repo_paths_are_derived_once(self):
        targets = derive_worktrees([REPO, REPO + os.sep], 6, "Plan")
        self.assertEqual(len(targets), 1)

    def test_existing_path_is_refused_not_suffixed(self):
        target = derive_worktree(REPO, 6, "Plan")
        with self.assertRaises(WorktreeCollision) as caught:
            derive_worktrees([REPO], 6, "Plan", exists=lambda path: path == target.worktree_path)
        self.assertIn(target.worktree_path, str(caught.exception))

    def test_free_paths_return_targets(self):
        targets = derive_worktrees([REPO], 6, "Plan", exists=lambda path: False)
        self.assertEqual(
            targets,
            [WorktreeTarget(REPO, os.path.join(ROOT, "lazyplan--plan-6-plan"), "plan/6-plan")],
        )
