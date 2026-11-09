"""Start and finish an agent work session."""

from __future__ import annotations

import os
import tempfile
import unittest

from lazyplan.services.agent_work import finish_work, start_work
from lazyplan.store import ClaimConflict, Store


class TestAgentWork(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(os.path.join(self.tmp.name, "work.db"))
        self.plan = self.store.add_plan("P", "what", goal="why", actor="fixture")
        self.milestone = self.store.add_milestone(self.plan.id, "M", actor="fixture")
        self.task = self.store.add_task(self.milestone.id, "T", "Commit: one.", actor="fixture")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_start_claims_and_opens_a_session(self) -> None:
        started = start_work(
            self.store,
            self.task.id,
            actor="alice",
            cwd=self.tmp.name,
        )
        self.assertEqual(self.store.get_task(self.task.id).status.value, "doing")
        self.assertIsNotNone(self.store.get_claim(self.task.id))
        self.assertIn("Work on T", started["prompt"])
        self.assertIn("P", started["prompt"])
        session = self.store.get_session(started["session"].id)
        assert session is not None
        self.assertEqual(session.actor, "alice")
        self.assertEqual(session.plan_id, self.plan.id)
        self.assertEqual(session.branch, started["branch"])

    def test_start_refuses_another_claim(self) -> None:
        self.store.claim_task(self.task.id, "bob", 300)
        with self.assertRaises(ClaimConflict):
            start_work(self.store, self.task.id, actor="alice", cwd=self.tmp.name)

    def test_finish_closes_the_run_and_session(self) -> None:
        started = start_work(self.store, self.task.id, actor="alice", cwd=self.tmp.name)
        run = self.store.add_agent_run(
            "ses_1",
            lazyplan_session_id=started["session"].id,
            plan_id=self.plan.id,
            task_id=self.task.id,
            title="Work T1",
            cwd=self.tmp.name,
            actor="agent",
        )
        ended = finish_work(
            self.store,
            run["id"],
            actor="alice",
            summary="did it",
            handoff="next: T2",
        )
        self.assertEqual(ended["status"], "done")
        session = self.store.get_session(started["session"].id)
        assert session is not None
        self.assertGreater(session.ended_at, 0)
        self.assertEqual(session.handoff, "next: T2")


if __name__ == "__main__":
    unittest.main()
