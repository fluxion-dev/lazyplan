"""Ship note rendering: sections, escaping, determinism, and caps."""

from __future__ import annotations

import unittest

from lazyplan.core.policies.ship import render

PAYLOAD = {
    "plan": {"id": 1, "name": "P | one", "status": "done"},
    "why": "Because",
    "milestones": [{"id": 1, "title": "M", "status": "done", "done": 1, "total": 1}],
    "tasks": {"done": 1, "total": 2},
    "done_tasks": [{"id": 1, "title": "Shipped"}],
    "open_tasks": [{"id": 2, "title": "Open"}],
    "criteria": {"total": 2, "evidence": 1},
    "open_criteria": [{"text": "Still open"}],
    "audit": {
        "coverage": 1.0,
        "trace_coverage": 1.0,
        "evidence_total": 3,
    },
    "commits": [{"sha": "a" * 40, "subject": "one"}],
    "prs": [{"number": 7, "title": "PR", "url": "https://x/7", "state": "merged"}],
    "questions": [{"id": 3, "text": "Why?"}],
    "blocked": [{"id": 4, "title": "Blocked"}],
    "stale": 1,
    "notes": [{"actor": "ana", "text": "note"}],
}


class TestShipPolicy(unittest.TestCase):
    def test_sections_and_values(self) -> None:
        text = render(PAYLOAD)
        for heading in (
            "## Why",
            "## What shipped",
            "## Evidence",
            "## Commits",
            "## Pull requests",
            "## Residual risks",
            "## Follow-ups",
        ):
            self.assertIn(heading, text)
        self.assertIn("P \\| one", text)
        self.assertIn("1/2 criteria proven", text)
        self.assertIn("T1 Shipped", text)
        self.assertIn("T2 Open", text)
        self.assertIn("Q3: Why?", text)
        self.assertIn("T4 Blocked", text)
        self.assertIn("Stale commits: 1", text)

    def test_output_is_deterministic(self) -> None:
        self.assertEqual(render(PAYLOAD), render(PAYLOAD))

    def test_max_chars_drops_optional_sections(self) -> None:
        full = render(PAYLOAD)
        tight = render(PAYLOAD, max_chars=450)
        self.assertLessEqual(len(tight), 450)
        self.assertNotEqual(full, tight)
        self.assertIn("## Why", tight)
        self.assertIn("[truncated to 200 chars]", render(PAYLOAD, max_chars=200))


if __name__ == "__main__":
    unittest.main()
