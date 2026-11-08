"""Manual override audit rows: actor, kind, target, reason, and the cap."""

from __future__ import annotations

import os
import tempfile
import unittest

from lazyplan.services.overrides import MAX_DETAIL, record_override
from lazyplan.store import Store


class TestOverrideAudit(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(os.path.join(self.tmp.name, "audit.db"))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _events(self) -> list[dict]:
        return [event for event in self.store.feed() if event["kind"] == "override"]

    def test_one_event_with_actor_target_and_reason(self) -> None:
        record_override(self.store, "approve", "plan #7", "reviewed the cut")
        events = self._events()
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event["actor"], "tui")
        self.assertEqual(event["kind"], "override")
        self.assertEqual(event["action"], "approve")
        self.assertIn("plan #7", event["detail"])
        self.assertIn("reviewed the cut", event["detail"])

    def test_reason_is_optional(self) -> None:
        record_override(self.store, "status", "task #3")
        detail = self._events()[0]["detail"]
        self.assertEqual(detail, "task #3: status")

    def test_detail_is_capped(self) -> None:
        record_override(self.store, "edit", "task #3", "x" * (MAX_DETAIL * 2))
        detail = self._events()[0]["detail"]
        self.assertEqual(len(detail), MAX_DETAIL)

    def test_one_call_writes_one_event(self) -> None:
        record_override(self.store, "claim release", "T9")
        record_override(self.store, "claim release", "T9")
        self.assertEqual(len(self._events()), 2)


if __name__ == "__main__":
    unittest.main()
