"""Pure agent row formatting: ranking, widths, statuses, and summaries."""

from __future__ import annotations

import unittest
from dataclasses import replace

from lazyplan.core.entities import Agent

try:
    from rich.console import Console

    from lazyplan.presentation.tui.views.agents import (
        agent_line,
        agents_summary,
        rank_agents,
    )
except ImportError:  # pragma: no cover - rich not installed
    agent_line = rank_agents = agents_summary = None  # type: ignore[assignment]


def plain(markup: str) -> str:
    console = Console(record=True, width=400, force_terminal=False)
    console.print(markup, end="")
    return console.export_text()


@unittest.skipUnless(agent_line is not None, "rich not installed")
class TestAgentLine(unittest.TestCase):
    def setUp(self) -> None:
        self.now = 1_000_000.0
        self.working = Agent(
            id=1,
            host="opencode",
            host_session="session-0001",
            agent="builder",
            plan_id=7,
            task_id=94,
            branch="plan/7-agent-registry",
            worktree="/repo-wt",
            started_at=self.now - 900,
            status="working",
        )
        self.waiting = replace(self.working, id=2, agent="reviewer", status="waiting")
        self.blocked = replace(self.working, id=3, agent="helper", status="blocked")
        self.lost = replace(self.working, id=4, agent="ghost", status="lost")
        self.ended = replace(self.working, id=5, agent="done", status="ended", ended_at=1.0)

    def test_ranks_waiting_first_then_working_and_lost(self) -> None:
        ranked = rank_agents([self.lost, self.working, self.waiting, self.blocked], self.now)
        self.assertEqual([row.id for row in ranked], [2, 1, 3, 4])

    def test_line_carries_agent_plan_task_branch_and_status(self) -> None:
        line = plain(agent_line(self.working, self.now, plan_title="Agent registry"))
        for expected in ("@builder", "A1", "P7", "T94", "Agent registry", "plan/7-agent-registry"):
            self.assertIn(expected, line)
        self.assertIn("working", line)

    def test_waiting_working_blocked_and_lost_have_distinct_glyphs(self) -> None:
        self.assertIn("◆", plain(agent_line(self.waiting, self.now)))
        self.assertIn("◐", plain(agent_line(self.working, self.now)))
        self.assertIn("⊘", plain(agent_line(self.blocked, self.now)))
        self.assertIn("✕", plain(agent_line(self.lost, self.now)))

    def test_unbound_row_names_its_reason(self) -> None:
        row = replace(
            self.working,
            plan_id=None,
            task_id=None,
            worktree="",
            unbound_reason="/repo is not a registered plan worktree",
        )
        line = plain(agent_line(row, self.now))
        self.assertIn("unbound", line)
        self.assertIn("A1", line)

    def test_no_branch_falls_back_to_a_dash(self) -> None:
        line = plain(agent_line(replace(self.working, branch=""), self.now))
        self.assertIn(" · - · ", line)

    def test_narrow_width_truncates_every_row_to_the_budget(self) -> None:
        for width in range(100, 220, 10):
            line = plain(
                agent_line(self.working, self.now, plan_title="A very long plan title", width=width)
            )
            self.assertLessEqual(len(line), width + 6, width)

    def test_summary_counts_open_waiting_lost_and_unbound(self) -> None:
        rows = [self.working, self.waiting, self.lost]
        summary = agents_summary(rows, self.now)
        self.assertIn("3 open", summary)
        self.assertIn("1 waiting", summary)
        self.assertIn("1 lost", summary)

    def test_summary_counts_unbound_rows(self) -> None:
        row = replace(self.working, plan_id=None, worktree="")
        self.assertIn("1 unbound", agents_summary([row], self.now))


if __name__ == "__main__":
    unittest.main()
