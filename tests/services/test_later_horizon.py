"""Later horizon end-to-end: sessions, overlaps, refs, and ship."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from lazyplan import services
from lazyplan.core.errors import TouchpointOverlap
from lazyplan.services import context, ship
from lazyplan.store import Store


class TestLaterHorizon(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir()
        self.checkout = mock.patch(
            "lazyplan.infrastructure.checkout.checkout_path", return_value=self.repo
        )
        self.checkout.start()
        self.store = Store(os.path.join(self.tmp.name, "later.db"))
        self.plan = self.store.add_plan("Later", "what", goal="why", actor="ana")
        self.milestone = self.store.add_milestone(self.plan.id, "M", actor="ana")
        self.first = self.store.add_task(self.milestone.id, "First", actor="ana")
        self.second = self.store.add_task(self.milestone.id, "Second", actor="ana")

    def tearDown(self) -> None:
        self.checkout.stop()
        self.tmp.cleanup()

    def test_agent_records_work_and_hands_off(self) -> None:
        agent = self.store.add_agent(
            "ana", host="opencode", agent="ana", host_session="host-1", plan_id=self.plan.id
        )
        self.store.transition_agent(agent.id, "working", event="prompt-submit")
        self.store.end_agent(agent.id, "ana", summary="shipped", handoff="next: QA")
        events = [event.event for event in self.store.agent_events(agent.id)]
        self.assertEqual(events, ["session-end", "prompt-submit", "start"])
        packet = context.build(self.store)
        self.assertEqual(packet["plans"][0]["previous_session"]["handoff"], "next: QA")

    def test_overlap_selection_and_refs_and_ship(self) -> None:
        self.store.add_touchpoint(self.first.id, "src/store")
        self.store.add_touchpoint(self.second.id, "src/tui")
        self.store.add_repo_link("task", self.first.id, "/repo", actor="ana")
        self.store.add_repo_link("task", self.second.id, "/repo", actor="ana")
        services.start_claim(self.store, self.first.id, "ana", repo_path="/repo")
        result = services.claim_next(self.store, "bob")
        assert result is not None
        self.assertEqual(result["task"]["id"], self.second.id)
        third = self.store.add_task(self.milestone.id, "Third", actor="ana")
        self.store.add_touchpoint(third.id, "src/store/base.py")
        self.store.add_repo_link("task", third.id, "/repo", actor="ana")
        with self.assertRaises(TouchpointOverlap):
            services.start_claim(self.store, third.id, "cara", repo_path="/repo")

        ref = self.store.link_ref(
            self.plan.id, "https://github.com/o/r/issues/7", title="Epic", actor="ana"
        )
        dump = services.export_all(self.store)
        self.assertEqual(dump["plans"][0]["refs"][0]["url"], ref.url)
        with tempfile.TemporaryDirectory() as other:
            target = Store(os.path.join(other, "target.db"))
            counts = services.import_all(target, dump, actor="fixture")
            self.assertEqual(counts["refs"], 1)
            self.assertEqual(target.list_refs(target.list_plans()[0].id)[0].title, "Epic")

        note = ship.build(self.store, self.plan.id)
        assert note is not None
        self.assertIn("## What shipped", note.markdown)
        self.assertIn("## Residual risks", note.markdown)
        self.assertEqual(note.payload["criteria"]["evidence"], 0)
        json.dumps(note.payload)


if __name__ == "__main__":
    unittest.main()
