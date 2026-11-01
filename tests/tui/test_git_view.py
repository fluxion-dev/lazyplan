"""The GIT pane document is pure, bounded, and uses the shared icon family."""

from __future__ import annotations

import unittest

from lazyplan.tui.views.git import build_git


class GitDocumentTest(unittest.TestCase):
    def test_empty_selection_offers_the_source_trail(self) -> None:
        document = build_git({})
        self.assertIn("no linked checkouts", document.render())
        self.assertIn("g opens the source trail", document.render())
        self.assertEqual(document.summary, "")

    def test_repo_state_uses_icons_and_tracking(self) -> None:
        full = {"effective_repos": [{"repo_path": "/x/web", "repo_remote": ""}]}
        states = [
            {
                "name": "web",
                "path": "/x/web",
                "branch": "main",
                "dirty": False,
                "ahead": 2,
                "behind": 1,
            }
        ]
        document = build_git(full, states)
        body = document.render()
        self.assertIn("⎇ web", body)
        self.assertIn("main", body)
        self.assertIn("○ clean", body)
        self.assertIn("↑2 ↓1", body)
        self.assertIn("1 repos", document.summary)

    def test_dirty_detached_and_commit_lines(self) -> None:
        full = {
            "effective_links": [
                {"sha": "a" * 40, "subject": "Render diffs", "files": ["a.py", "b.py"]},
                {"sha": "b" * 40, "subject": "Old work", "stale": True},
            ],
            "effective_forge_links": [
                {
                    "number": 42,
                    "title": "Render diffs in place",
                    "state": "merged",
                    "checks": "pass",
                }
            ],
        }
        states = [{"name": "web", "branch": "", "dirty": True, "detached": True}]
        body = build_git(full, states).render()
        self.assertIn("⊘ detached", body)
        self.assertIn("◆ aaaaaaaaaaaa", body)
        self.assertIn("2 files", body)
        self.assertIn("stale", body)
        self.assertIn("⇄ PR #42", body)
        self.assertIn("checks pass", body)

    def test_overflow_is_folded_into_one_count_line(self) -> None:
        full = {
            "effective_links": [
                {"sha": f"{number:040d}", "subject": f"Commit {number}"} for number in range(7)
            ],
            "effective_forge_links": [
                {"number": number, "title": f"PR {number}", "state": "open"} for number in range(5)
            ],
        }
        body = build_git(full).render()
        self.assertIn("+3 more commits", body)
        self.assertIn("2 more PRs", body)
        self.assertEqual(body.count("◆"), 4)
        self.assertEqual(body.count("⇄"), 3)


if __name__ == "__main__":
    unittest.main()
