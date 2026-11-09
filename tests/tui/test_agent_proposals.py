"""Proposal review and the workbench entry point."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from textual.widgets import Button

from lazyplan.infrastructure.agents import AgentProfile
from lazyplan.presentation.tui import create_app
from lazyplan.presentation.tui.screens.agent import AgentScreen
from lazyplan.presentation.tui.screens.agent_proposals import ProposalReviewScreen
from lazyplan.store import Store

ROOT = Path(__file__).resolve().parents[2]
FAKE = ROOT / "tests" / "support" / "fake_acp.py"


def document(title: str) -> dict:
    return {
        "plan": {"key": "p1", "title": title, "why": "why", "what": "what"},
        "milestones": [],
    }


class TestProposalReview(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / "proposals.db")
        self.store = Store(self.db)
        self.plan = self.store.add_plan("P", "what", goal="why", actor="fixture")
        self.milestone = self.store.add_milestone(self.plan.id, "M", actor="fixture")
        self.proposal = self.store.add_proposal(
            "plan_document",
            "Draft",
            {"document": document("Draft")},
            actor="agent",
        )

    async def asyncTearDown(self) -> None:
        self.tmp.cleanup()

    async def test_apply_proposal_from_the_review_screen(self) -> None:
        app = create_app(self.db)
        async with app.run_test() as pilot:
            app.push_screen(ProposalReviewScreen(self.store))
            await pilot.pause()
            app.screen.query_one("#proposal-apply", Button).press()
            await pilot.pause()
            self.assertEqual(self.store.get_proposal(self.proposal["id"])["status"], "applied")
            self.assertEqual(self.store.counts()["plans"], 2)

    async def test_workbench_opens_the_proposal_review(self) -> None:
        app = create_app(self.db)
        async with app.run_test() as pilot:
            screen = AgentScreen(
                AgentProfile("fake", "Fake", (sys.executable, str(FAKE))),
                ROOT,
                store=self.store,
            )
            app.push_screen(screen)
            await pilot.pause()
            screen.query_one("#agent-proposals", Button).press()
            await pilot.pause()
            self.assertEqual(app.screen.__class__.__name__, "ProposalReviewScreen")


if __name__ == "__main__":
    unittest.main()
