"""Agent-run records."""

from __future__ import annotations

import os
import tempfile
import unittest

from lazyplan.store import Store


class TestAgentRuns(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(os.path.join(self.tmp.name, "runs.db"))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_start_and_end_a_run(self) -> None:
        plan = self.store.add_plan("P", "what", goal="why", actor="fixture")
        milestone = self.store.add_milestone(plan.id, "M", actor="fixture")
        task = self.store.add_task(milestone.id, "T", actor="fixture")
        session = self.store.start_session("alice", plan_id=plan.id)[0]
        run = self.store.add_agent_run(
            "ses_1",
            lazyplan_session_id=session.id,
            plan_id=plan.id,
            task_id=task.id,
            title="Work T1",
            cwd="/repo",
            actor="agent",
        )
        self.assertEqual(run["status"], "running")
        self.assertEqual(self.store.list_agent_runs()[0]["id"], run["id"])
        ended = self.store.end_agent_run(
            run["id"], summary="did it", handoff="next: T2", actor="alice"
        )
        self.assertEqual(ended["status"], "done")
        self.assertEqual(ended["summary"], "did it")
        self.assertEqual(ended["handoff"], "next: T2")
        self.assertEqual(self.store.list_agent_runs(), [])


if __name__ == "__main__":
    unittest.main()
