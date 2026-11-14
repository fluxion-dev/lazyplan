"""Plan worktree derivation: slugs, sibling paths, collisions."""

from __future__ import annotations

import os
import unittest

from lazyplan.core.policies.worktrees import (
    LaneWorktreeTarget,
    WorktreeCollision,
    WorktreeTarget,
    derive_lane_worktree,
    derive_lane_worktrees,
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
        for path in (
            "lazyplan",
            os.path.join("repos", "lazyplan"),
            "C:lazyplan",
            "C:repos\\lazyplan",
        ):
            with self.subTest(path=path), self.assertRaises(ValueError):
                derive_worktree(path, 6, "Plan")

    def test_accepts_drive_paths_at_any_depth(self):
        cases = {
            "C:\\lazyplan": "C:\\lazyplan--plan-6-plan",
            "C:\\Users\\me\\repos\\lazyplan": "C:\\Users\\me\\repos\\lazyplan--plan-6-plan",
            "D:/work/lazyplan": "D:/work/lazyplan--plan-6-plan",
        }
        for repo, worktree in cases.items():
            with self.subTest(repo=repo):
                self.assertEqual(derive_worktree(repo, 6, "Plan").worktree_path, worktree)


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


class TestDeriveLaneWorktree(unittest.TestCase):
    def test_derives_a_sibling_path_and_branch_per_lane(self):
        target = derive_lane_worktree(REPO, 7, "Lanes", 58, "Lane model")

        self.assertEqual(target.repo_path, REPO)
        self.assertEqual(
            target.worktree_path,
            os.path.join(ROOT, "lazyplan--plan-7-lanes-m58-lane-model"),
        )
        self.assertEqual(target.branch, "plan/7-lanes--m58-lane-model")
        self.assertEqual(target.milestone_id, 58)

    def test_same_titles_stay_unique_by_milestone_id(self):
        first = derive_lane_worktree(REPO, 7, "Lanes", 1, "Build")
        second = derive_lane_worktree(REPO, 7, "Lanes", 2, "Build")
        self.assertNotEqual(first.worktree_path, second.worktree_path)
        self.assertNotEqual(first.branch, second.branch)

    def test_multi_repo_lanes_get_one_target_each(self):
        other = os.path.join(ROOT, "site")
        targets = derive_lane_worktrees([REPO, other], 7, "Lanes", 58, "Lane model")
        self.assertEqual([item.repo_path for item in targets], [REPO, other])

    def test_existing_lane_path_is_refused_not_suffixed(self):
        target = derive_lane_worktree(REPO, 7, "Lanes", 58, "Lane model")
        with self.assertRaises(WorktreeCollision):
            derive_lane_worktrees([REPO], 7, "Lanes", 58, "Lane model", exists=lambda path: True)
        self.assertEqual(target.milestone_id, 58)

    def test_duplicate_repo_paths_are_derived_once(self):
        targets = derive_lane_worktrees([REPO, REPO + os.sep], 7, "Lanes", 58, "Lane model")
        self.assertEqual(
            targets,
            [
                LaneWorktreeTarget(
                    REPO,
                    os.path.join(ROOT, "lazyplan--plan-7-lanes-m58-lane-model"),
                    "plan/7-lanes--m58-lane-model",
                    58,
                )
            ],
        )
