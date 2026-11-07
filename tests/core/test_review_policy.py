"""Pure review-packet Markdown rendering."""

from __future__ import annotations

import unittest

from lazyplan.core.policies.review import render


def payload() -> dict:
    return {
        "plan": {"id": 1, "name": "Plan", "status": "doing"},
        "approval": {
            "revision": 2,
            "approved_at": 0,
            "actor": "brad",
            "drift": 1,
        },
        "readiness": {"ready": False, "checks": []},
        "why": "Because.",
        "what": "The work.",
        "criteria": [
            {
                "id": 10,
                "kind": "plan",
                "text": "Works | offline",
                "done": False,
                "tasks": [{"id": 1, "title": "T"}],
                "commits": [{"sha": "a" * 40, "subject": "work"}],
                "prs": [{"number": 7, "title": "PR", "state": "open"}],
                "evidence": "pass",
            }
        ],
        "milestones": [
            {
                "id": 2,
                "title": "M",
                "status": "doing",
                "tasks": [{"id": 1, "title": "T", "status": "doing"}],
            }
        ],
        "commits": [{"sha": "a" * 40, "subject": "work"}],
        "prs": [{"number": 7, "title": "PR", "state": "open", "url": "https://x/7"}],
        "lint": [{"rule": "missing-verification", "severity": "warn", "message": "needs a check"}],
        "audit": {"coverage": 1.0, "trace_coverage": 1.0, "evidence_coverage": 0.5},
        "questions": [{"id": 3, "text": "Which host?"}],
        "notes": [{"actor": "brad", "text": "handoff"}],
    }


class TestReviewRender(unittest.TestCase):
    def test_sections_and_table(self) -> None:
        text = render(payload())
        self.assertIn("# P1 — Plan", text)
        self.assertIn("**Revision:** r2", text)
        self.assertIn("**Readiness:** not ready", text)
        self.assertIn("## Acceptance criteria", text)
        self.assertIn(r"Works \| offline", text)
        self.assertIn("| no | T1 | 1 | 1 | pass |", text)
        self.assertIn("## Milestones and tasks", text)
        self.assertIn("## Commits", text)
        self.assertIn("## Open questions", text)
        self.assertIn("Q3: Which host?", text)

    def test_deterministic(self) -> None:
        self.assertEqual(render(payload()), render(payload()))

    def test_max_chars_is_enforced(self) -> None:
        text = render(payload(), max_chars=200)
        self.assertLessEqual(len(text), 200)
        self.assertIn("truncated", text)

    def test_empty_sections_are_explicit(self) -> None:
        data = payload()
        data["commits"] = []
        data["prs"] = []
        data["questions"] = []
        data["notes"] = []
        text = render(data)
        self.assertIn("none linked", text)
        self.assertIn("## Open questions\n\nnone", text)


if __name__ == "__main__":
    unittest.main()
