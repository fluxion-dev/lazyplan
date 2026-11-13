"""Pure claim row formatting: order, widths, and the summary."""

from __future__ import annotations

import unittest

try:
    from rich.console import Console

    from lazyplan.presentation.tui.views.agents import (
        claim_line,
        claims_summary,
        rank_claims,
    )
except ImportError:  # pragma: no cover - rich not installed
    claim_line = rank_claims = claims_summary = None  # type: ignore[assignment]


def plain(markup: str) -> str:
    console = Console(record=True, width=400, force_terminal=False)
    console.print(markup, end="")
    return console.export_text()


def claim(task_id: int, actor: str, started_at: float, **fields: object) -> dict:
    row: dict = {
        "task_id": task_id,
        "actor": actor,
        "started_at": started_at,
        "task_title": f"Task {task_id}",
        "plan_id": 3,
        "plan_title": "Agents from claims",
    }
    row.update(fields)
    return row


@unittest.skipUnless(claim_line is not None, "rich not installed")
class TestClaimLine(unittest.TestCase):
    def setUp(self) -> None:
        self.now = 1_000_000.0

    def test_line_names_actor_task_plan_and_age(self) -> None:
        text = plain(claim_line(claim(12, "claude", self.now - 300), self.now))
        self.assertEqual(text, "@claude T12 Task 12 · P3 Agents from claims · 5m")

    def test_ages_past_an_hour_read_hours_and_minutes(self) -> None:
        text = plain(claim_line(claim(12, "claude", self.now - 3_900), self.now))
        self.assertTrue(text.endswith("1h05m"))

    def test_newest_claim_comes_first(self) -> None:
        rows = [claim(1, "a", self.now - 600), claim(2, "b", self.now - 60)]
        self.assertEqual([row["task_id"] for row in rank_claims(rows)], [2, 1])

    def test_narrow_width_truncates_titles_to_the_budget(self) -> None:
        row = claim(12, "claude", self.now, task_title="T" * 80, plan_title="P" * 80)
        for width in (40, 60, 90):
            with self.subTest(width=width):
                self.assertLessEqual(len(plain(claim_line(row, self.now, width))), width)

    def test_markup_in_titles_and_actors_is_escaped(self) -> None:
        row = claim(12, "[bold]x", self.now, task_title="[red]t", plan_title="[dim]p")
        text = plain(claim_line(row, self.now))
        self.assertIn("@[bold]x", text)
        self.assertIn("[red]t", text)

    def test_summary_counts_tasks_and_distinct_agents(self) -> None:
        rows = [claim(1, "a", 0), claim(2, "a", 0), claim(3, "b", 0)]
        self.assertEqual(claims_summary(rows), "3 tasks · 2 agents")
        self.assertEqual(claims_summary(rows[:1]), "1 task · 1 agent")


if __name__ == "__main__":
    unittest.main()
