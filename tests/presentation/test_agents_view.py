"""The agents card rows: order, compact fields, truncation, and glyphs."""

from __future__ import annotations

import unittest
from dataclasses import replace

from lazyplan.core.entities import Session
from lazyplan.presentation.shared.design import SPINNER_FRAMES

try:
    from lazyplan.presentation.tui.views.agents import (
        rank_sessions,
        session_line,
        sessions_summary,
    )
except ImportError:  # pragma: no cover - stdlib-only interpreter
    rank_sessions = session_line = sessions_summary = None  # type: ignore[assignment]


def plain(line: str) -> str:
    """Visible row text, with Rich markup removed."""
    from rich.text import Text

    return Text.from_markup(line).plain


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
            last_seen_at=self.now - 130,
            phase="working",
        )

    def test_awaiting_sorts_first_then_working_then_idle(self) -> None:
        ranked = rank_sessions([self.idle, self.working, self.awaiting], self.now)
        self.assertEqual([row.id for row in ranked], [2, 1, 3])

    def test_the_row_is_agent_id_plan_branch_age_and_glyph(self) -> None:
        line = plain(session_line(self.working, self.now, plan_title="Agents pane"))
        self.assertEqual(line, "@ana 7f3a · P3 Agents pane · task/one · 10m · ⠋")

    def test_the_row_drops_the_clock_session_task_and_state_words(self) -> None:
        line = plain(session_line(replace(self.working, branch="task/157-pane"), self.now))
        self.assertNotIn("S1", line)
        self.assertNotIn("T157", line)
        self.assertNotIn("via", line)
        self.assertNotIn("opencode", line)
        for word in ("working", "awaiting", "stale", "idle"):
            self.assertNotIn(word, line)
        self.assertNotRegex(line, r"\b\d{2}:\d{2}\b")

    def test_every_state_has_its_glyph(self) -> None:
        self.assertEqual(plain(session_line(self.working, self.now)).rsplit(" · ", 1)[-1], "⠋")
        self.assertEqual(plain(session_line(self.awaiting, self.now)).rsplit(" · ", 1)[-1], "◆")
        self.assertEqual(plain(session_line(self.stale, self.now)).rsplit(" · ", 1)[-1], "◌")
        self.assertEqual(plain(session_line(self.idle, self.now)).rsplit(" · ", 1)[-1], "◌")

    def test_the_frame_selects_the_working_glyph(self) -> None:
        line = plain(session_line(self.working, self.now, frame=3))
        self.assertTrue(line.endswith(f"· {SPINNER_FRAMES[3]}"))

    def test_a_static_frame_shows_a_still_working_glyph(self) -> None:
        line = plain(session_line(self.working, self.now, frame=None))
        self.assertTrue(line.endswith("· ◐"))

    def test_rows_without_a_plan_branch_or_host_use_dashes(self) -> None:
        session = Session(id=9, actor="ana", started_at=self.now)
        line = plain(session_line(session, self.now))
        self.assertEqual(line, "@ana - · - · - · 0m · ⠋")

    def test_host_sessions_keep_their_last_four_characters(self) -> None:
        other = replace(self.working, id=5, host_session="ses_c2d1")
        first = plain(session_line(self.working, self.now))
        second = plain(session_line(other, self.now))
        self.assertIn("7f3a", first)
        self.assertIn("c2d1", second)
        self.assertEqual(len({first, second}), 2)

    def test_a_narrow_row_truncates_plan_and_branch_with_an_ellipsis(self) -> None:
        session = replace(
            self.working,
            branch="feature/very-long-branch-name",
        )
        title = "A very long plan title that will truncate"
        for width in (40, 60, 100):
            with self.subTest(width=width):
                line = plain(session_line(session, self.now, plan_title=title, width=width))
                self.assertLessEqual(len(line), width)
                if len(title) + len(session.branch) + 28 > width:
                    self.assertIn("…", line)

    def test_a_tiny_width_still_never_overflows(self) -> None:
        session = replace(self.working, branch="feature/very-long-branch-name")
        line = plain(
            session_line(
                session,
                self.now,
                plan_title="A very long plan title",
                width=30,
            )
        )
        self.assertLessEqual(len(line), 30)
        self.assertIn("f…", line)

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
