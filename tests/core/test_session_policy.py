"""Session policy: ids, summaries, handoffs, and duration."""

from __future__ import annotations

import unittest

from lazyplan.core.entities import Session
from lazyplan.core.policies.sessions import (
    HANDOFF_LIMIT,
    SUMMARY_LIMIT,
    auto_close_summary,
    normalize_handoff,
    normalize_phase,
    normalize_summary,
    parse_session_id,
    phase_for_event,
    supersede_summary,
)


class TestSessionPolicy(unittest.TestCase):
    def test_parse_session_id_accepts_prefixed_and_bare_ids(self) -> None:
        for text, want in (("S12", 12), ("s12", 12), ("12", 12), (" S7 ", 7)):
            with self.subTest(text=text):
                self.assertEqual(parse_session_id(text), want)

    def test_parse_session_id_rejects_empty_zero_and_text(self) -> None:
        for text in ("", "S", "S0", "0", "-3", "abc"):
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    parse_session_id(text)

    def test_summary_and_handoff_are_trimmed(self) -> None:
        self.assertEqual(normalize_summary("  did it  "), "did it")
        self.assertEqual(normalize_handoff("\n next: T1 \n"), "next: T1")

    def test_long_summary_and_handoff_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            normalize_summary("x" * (SUMMARY_LIMIT + 1))
        with self.assertRaises(ValueError):
            normalize_handoff("x" * (HANDOFF_LIMIT + 1))

    def test_supersede_summary_names_the_new_session(self) -> None:
        self.assertEqual(supersede_summary(3, 4), "superseded by session S4")

    def test_session_duration_uses_now_while_open(self) -> None:
        session = Session(id=1, started_at=100.0)
        self.assertFalse(session.ended)
        self.assertEqual(session.duration(160.0), 60.0)
        closed = Session(id=1, started_at=100.0, ended_at=130.0)
        self.assertTrue(closed.ended)
        self.assertEqual(closed.duration(999.0), 30.0)

    def test_phase_and_stop_state(self) -> None:
        self.assertEqual(normalize_phase(" Awaiting "), "awaiting")
        with self.assertRaises(ValueError):
            normalize_phase("busy")
        self.assertEqual(phase_for_event("stop"), "awaiting")
        self.assertEqual(phase_for_event("prompt-submit"), "working")

    def test_awaiting_and_idle_follow_the_heartbeat(self) -> None:
        session = Session(id=1, started_at=100.0, phase="awaiting", last_seen_at=200.0)
        self.assertTrue(session.awaiting)
        self.assertEqual(session.last_activity(), 200.0)
        self.assertEqual(session.idle_seconds(260.0), 60.0)
        self.assertFalse(Session(id=1, ended_at=10.0).awaiting)

    def test_auto_close_summary_names_the_idle_hours(self) -> None:
        self.assertEqual(auto_close_summary(0), "auto-closed after 1h idle")
        self.assertEqual(auto_close_summary(5 * 3600), "auto-closed after 5h idle")


if __name__ == "__main__":
    unittest.main()
