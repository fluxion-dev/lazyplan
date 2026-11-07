"""Session policy: ids, summaries, handoffs, and duration."""

from __future__ import annotations

import unittest

from lazyplan.core.entities import Session
from lazyplan.core.policies.sessions import (
    HANDOFF_LIMIT,
    SUMMARY_LIMIT,
    normalize_handoff,
    normalize_summary,
    parse_session_id,
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


if __name__ == "__main__":
    unittest.main()
