"""Context packet: active slice, proof, and deterministic budget trimming."""

from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from lazyplan import services
from lazyplan.core.entities import Status
from lazyplan.services import context
from lazyplan.store import Store


class ContextTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "t.db")
        self.plan = self.store.add_plan("Plan", "the what", goal="the why")
        self.milestone = self.store.add_milestone(self.plan.id, "M", "desc")
        self.doing = self.store.add_task(self.milestone.id, "Doing task", "desc")
        self.next_one = self.store.add_task(self.milestone.id, "Next one", "desc")
        self.next_two = self.store.add_task(self.milestone.id, "Next two", "desc")
        self.next_three = self.store.add_task(self.milestone.id, "Next three", "desc")
        self.next_four = self.store.add_task(self.milestone.id, "Next four", "desc")
        services.set_status(self.store, "task", self.doing.id, Status.DOING, actor="t")
        services.set_status(self.store, "milestone", self.milestone.id, Status.DOING, actor="t")
        services.set_status(self.store, "plan", self.plan.id, Status.DOING, actor="t")
        self.store.add_criteria("plan", self.plan.id, "works")
        self.store.add_criteria("task", self.doing.id, "task tests pass")
        self.store.add_note("plan", self.plan.id, "decision", actor="alice")
        self.store.add_comment("task", self.doing.id, "please check", actor="rev")
        self.store.claim_task(self.doing.id, "alice", 300)
        self.store.link_commit(
            "task", self.doing.id, "a" * 40, subject="linked", timestamp=1000, actor="t"
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_packet_contains_the_active_slice(self):
        payload = context.build(self.store)
        self.assertEqual(payload["active"], 1)
        plan = payload["plans"][0]
        self.assertEqual(plan["why"], "the why")
        self.assertEqual(plan["what"], "the what")
        self.assertEqual(plan["doing"][0]["title"], "Doing task")
        self.assertEqual(plan["doing"][0]["claim"]["actor"], "alice")
        self.assertEqual(
            [task["title"] for task in plan["next"]], ["Next one", "Next two", "Next three"]
        )
        self.assertIn("works", [item["text"] for item in plan["criteria"]])
        self.assertEqual(plan["notes"][0]["text"], "decision")
        self.assertEqual(plan["comments"][0]["text"], "please check")
        self.assertEqual(plan["commits"][0]["short"], "a" * 8)
        self.assertEqual(plan["claims"][0]["actor"], "alice")

    def test_questions_are_in_the_packet(self):
        question = self.store.add_question(self.plan.id, "Which host?")
        payload = context.build(self.store)
        self.assertEqual(payload["plans"][0]["questions"][0]["id"], question.id)
        self.assertIn("Which host?", "\n".join(context.lines(payload)))

    def test_questions_survive_trimming_longer_than_notes(self):
        self.store.add_question(self.plan.id, "Which host?")
        found = False
        for budget in range(150, 800, 10):
            payload = context.build(self.store, max_chars=budget)
            plan = payload["plans"][0] if payload["plans"] else {}
            if plan.get("id") != self.plan.id:
                continue
            if not plan.get("notes") and plan.get("questions"):
                found = True
                break
        self.assertTrue(found)

    def test_budget_is_deterministic_and_respected(self):
        full = context.build(self.store, max_chars=4000)
        tight = context.build(self.store, max_chars=200)
        self.assertFalse(full["truncated"])
        self.assertTrue(tight["truncated"])
        self.assertLessEqual(len(json.dumps(tight, ensure_ascii=False, separators=(",", ":"))), 200)
        self.assertEqual(tight["plans"][0]["id"], self.plan.id)

    def test_small_budget_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "max_chars"):
            context.build(self.store, max_chars=100)

    def test_text_lists_the_same_facts(self):
        text = "\n".join(context.lines(context.build(self.store)))
        self.assertIn("Doing task", text)
        self.assertIn("Next one", text)
        self.assertIn("open criteria", text)

    def test_query_count_is_bounded(self):
        with mock.patch("lazyplan.store.base.sqlite3.connect", wraps=sqlite3.connect) as connect:
            context.build(self.store)
        self.assertLessEqual(connect.call_count, 25)

    def test_previous_session_is_in_the_packet(self):
        agent = self.store.add_agent(
            "alice", host="opencode", agent="alice", plan_id=self.plan.id, now=100.0
        )
        self.store.end_agent(
            agent.id, "alice", summary="shipped the slice", handoff="next: run QA", now=200.0
        )
        payload = context.build(self.store)
        plan = payload["plans"][0]
        self.assertEqual(plan["previous_session"]["handoff"], "next: run QA")
        text = "\n".join(context.lines(payload))
        self.assertIn("shipped the slice", text)
        self.assertIn("next: run QA", text)

    def test_empty_store_is_empty(self):
        empty = Store(Path(self.tmp.name) / "empty.db")
        payload = context.build(empty)
        self.assertEqual(payload["active"], 0)
        self.assertEqual(context.lines(payload), ["no active plans"])

    def test_missing_plan_returns_empty(self):
        payload = context.build(self.store, plan_id=999)
        self.assertEqual(payload["plans"], [])


if __name__ == "__main__":
    unittest.main()
