"""Agent proposal persistence and application."""

from __future__ import annotations

import os
import tempfile
import unittest

from lazyplan.services import proposals as proposal_service
from lazyplan.store import Store


class TestProposals(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(os.path.join(self.tmp.name, "proposals.db"))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_add_list_get_and_resolve(self) -> None:
        proposal = self.store.add_proposal(
            "plan_document",
            "Draft",
            {"document": {"plan": {"title": "P"}}},
            summary="why",
            actor="agent",
        )
        self.assertEqual(proposal["status"], "pending")
        self.assertEqual([row["id"] for row in self.store.list_proposals()], [proposal["id"]])
        self.assertEqual(self.store.get_proposal(proposal["id"])["title"], "Draft")
        resolved = self.store.resolve_proposal(proposal["id"], "rejected", actor="human")
        self.assertEqual(resolved["status"], "rejected")
        with self.assertRaises(ValueError):
            self.store.resolve_proposal(proposal["id"], "applied")

    def test_apply_plan_document_creates_the_plan(self) -> None:
        document = {
            "plan": {
                "key": "p1",
                "title": "Proposed plan",
                "why": "why",
                "what": "what",
                "criteria": ["works"],
            },
            "milestones": [
                {
                    "key": "m1",
                    "title": "M1",
                    "desc": "As a user, I want it.",
                    "tasks": [
                        {
                            "key": "t1",
                            "title": "Do the work",
                            "desc": "Approach: do it.\n\nCommit: one.\n\nVerify: tests.",
                        }
                    ],
                }
            ],
        }
        proposal = self.store.add_proposal(
            "plan_document", "Proposed plan", {"document": document}, actor="agent"
        )
        result = proposal_service.apply_proposal(self.store, proposal["id"], actor="human")
        self.assertEqual(result["counts"]["milestones"], 1)
        self.assertEqual(self.store.counts()["plans"], 1)
        self.assertEqual(self.store.get_proposal(proposal["id"])["status"], "applied")

    def test_apply_row_edit_changes_only_that_row(self) -> None:
        plan = self.store.add_plan("P", "what", goal="why", actor="fixture")
        proposal = self.store.add_proposal(
            "row_edit",
            "Rename",
            {"kind": "plan", "id": plan.id, "title": "New name", "reason": "agent"},
            actor="agent",
        )
        proposal_service.apply_proposal(self.store, proposal["id"], actor="human")
        self.assertEqual(self.store.get_plan(plan.id).name, "New name")

    def test_apply_task_create(self) -> None:
        plan = self.store.add_plan("P", "what", goal="why", actor="fixture")
        milestone = self.store.add_milestone(plan.id, "M", actor="fixture")
        proposal = self.store.add_proposal(
            "task_create",
            "New task",
            {"milestone": milestone.id, "title": "T", "desc": "d"},
            actor="agent",
        )
        result = proposal_service.apply_proposal(self.store, proposal["id"], actor="human")
        self.assertEqual(result["milestone"], milestone.id)
        self.assertEqual(len(self.store.list_tasks(milestone.id)), 1)

    def test_reject_does_not_change_plan_rows(self) -> None:
        plan = self.store.add_plan("P", "what", goal="why", actor="fixture")
        proposal = self.store.add_proposal(
            "row_edit",
            "Rename",
            {"kind": "plan", "id": plan.id, "title": "New name"},
            actor="agent",
        )
        proposal_service.reject_proposal(self.store, proposal["id"], actor="human")
        self.assertEqual(self.store.get_plan(plan.id).name, "P")
        self.assertEqual(self.store.get_proposal(proposal["id"])["status"], "rejected")


if __name__ == "__main__":
    unittest.main()
