"""Agent policy: ids, statuses, transitions, and event mapping."""

from __future__ import annotations

import unittest

from lazyplan.core.entities import Agent
from lazyplan.core.policies.agents import (
    STATUSES,
    can_transition,
    parse_agent_id,
    parse_pid,
    status_for_event,
)
from lazyplan.core.policies.sessions import parse_session_id


class TestAgentPolicy(unittest.TestCase):
    def test_parse_agent_id_accepts_prefixed_and_bare_ids(self) -> None:
        for text, want in (("A12", 12), ("a12", 12), ("12", 12), (" A7 ", 7)):
            with self.subTest(text=text):
                self.assertEqual(parse_agent_id(text), want)

    def test_parse_agent_id_rejects_empty_zero_and_text(self) -> None:
        for text in ("", "A", "A0", "0", "-3", "abc"):
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    parse_agent_id(text)

    def test_session_ids_keep_their_own_prefix(self) -> None:
        self.assertEqual(parse_session_id("S12"), 12)
        self.assertEqual(parse_session_id("12"), 12)

    def test_parse_pid_is_non_negative(self) -> None:
        self.assertEqual(parse_pid("42"), 42)
        self.assertEqual(parse_pid(""), 0)
        self.assertEqual(parse_pid("-4"), 0)
        self.assertEqual(parse_pid("nope"), 0)

    def test_allowed_and_forbidden_transitions(self) -> None:
        self.assertIn("waiting", STATUSES)
        self.assertTrue(can_transition("starting", "working"))
        self.assertTrue(can_transition("working", "tool"))
        self.assertTrue(can_transition("lost", "ended"))
        self.assertTrue(can_transition("working", "working"))
        self.assertFalse(can_transition("ended", "working"))
        self.assertFalse(can_transition("lost", "working"))

    def test_every_host_event_maps_to_a_status(self) -> None:
        self.assertEqual(status_for_event("session-start"), "starting")
        self.assertEqual(status_for_event("prompt-submit"), "working")
        self.assertEqual(status_for_event("pre-tool"), "tool")
        self.assertEqual(status_for_event("post-tool"), "working")
        self.assertEqual(status_for_event("stop"), "waiting")
        self.assertEqual(status_for_event("pre-compact"), "compacting")
        self.assertEqual(status_for_event("session-end"), "ended")

    def test_agent_duration_uses_now_while_open(self) -> None:
        agent = Agent(id=1, started_at=100.0)
        self.assertTrue(agent.live)
        self.assertFalse(agent.ended)
        self.assertEqual(agent.duration(160.0), 60.0)
        closed = Agent(id=1, started_at=100.0, ended_at=130.0, status="ended")
        self.assertTrue(closed.ended)
        self.assertFalse(closed.live)
        self.assertEqual(closed.duration(999.0), 30.0)

    def test_lost_and_unbound_read_distinctly(self) -> None:
        lost = Agent(id=1, status="lost")
        self.assertTrue(lost.lost)
        self.assertFalse(lost.live)
        self.assertTrue(Agent(id=2).unbound)
        self.assertFalse(Agent(id=3, plan_id=1, worktree="/repo").unbound)
