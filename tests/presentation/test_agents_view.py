"""The agents card states: ordering, badges, and subtitle counts."""

from __future__ import annotations

import unittest
from dataclasses import replace

from lazyplan.core.entities import Session

try:
    from lazyplan.presentation.tui.views.agents import (
        rank_sessions,
        session_line,
        sessions_summary,
    )
except ImportError:  # pragma: no cover - stdlib-only interpreter
    rank_sessions = session_line = sessions_summary = None  # type: ignore[assignment]


@unittest.skipUnless(session_line is not None, "textual/rich not installed")
class AgentsViewTest(unittest.TestCase):
    def setUp(self) -> None:
        self.now = 1_000_000.0
        self.working = Session(
            id=1,
            actor="ana",
            plan_id=3,
            branch="task/one",
            started_at=self.now - 600,
            last_seen_at=self.now - 5,
            phase="working",
            host="opencode",
            host_session="ses_7f3a",
        )
        self.awaiting = Session(
            id=2,
            actor="bo",
            plan_id=4,
            started_at=self.now - 1200,
            last_seen_at=self.now - 60,
            phase="awaiting",
        )
        self.idle = Session(
            id=3,
            actor="ca",
            started_at=self.now - 90_000,
            last_seen_at=self.now - 50_000,
            phase="working",
        )
        self.stale = Session(
            id=4,
            actor="di",
            started_at=self.now - 2_000,
            last_seen_at=self.now - 1_000,
            phase="working",
        )

    def test_awaiting_sorts_first_then_working_then_idle(self) -> None:
        ranked = rank_sessions([self.idle, self.working, self.awaiting], self.now)
        self.assertEqual([row.id for row in ranked], [2, 1, 3])

    def test_session_line_badges_the_live_state(self) -> None:
        line = session_line(self.awaiting, self.now)
        self.assertIn("@bo", line)
        self.assertIn("S2", line)
        self.assertIn("P4", line)
        self.assertIn("awaiting you", line)
        self.assertIn("working", session_line(self.working, self.now))
        self.assertIn("idle", session_line(self.idle, self.now))
        self.assertIn("stale", session_line(self.stale, self.now))

    def test_session_line_labels_the_short_host_session(self) -> None:
        line = session_line(self.working, self.now)
        self.assertIn("via opencode", line)
        self.assertIn("7f3a", line)

    def test_rows_that_differ_only_by_host_session_stay_distinct(self) -> None:
        other = replace(self.working, id=5, host_session="ses_c2d1")
        first = session_line(self.working, self.now)
        second = session_line(other, self.now)
        self.assertIn("7f3a", first)
        self.assertIn("c2d1", second)
        self.assertEqual(len({first, second}), 2)

    def test_summary_counts_every_open_row(self) -> None:
        rows = [replace(self.working, id=10 + index) for index in range(6)]
        self.assertIn("6 open", sessions_summary(rows, self.now))

    def test_summary_counts_open_awaiting_and_idle(self) -> None:
        summary = sessions_summary([self.working, self.awaiting, self.idle], self.now)
        self.assertIn("3 open", summary)
        self.assertIn("1 awaiting", summary)
        self.assertIn("1 idle", summary)
        self.assertIn("1 stale", sessions_summary([self.stale], self.now))


if __name__ == "__main__":
    unittest.main()
