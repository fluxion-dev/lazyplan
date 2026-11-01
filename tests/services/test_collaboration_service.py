"""Collaboration use cases over the collaboration port."""

from __future__ import annotations

import os
import tempfile
import unittest

from lazyplan import services
from lazyplan.store import Store


class TestCollaborationService(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(os.path.join(self.tmp.name, "collab.db"))
        self.plan = self.store.add_plan("P", actor="fixture")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_note_round_trip(self) -> None:
        note = services.add_note(self.store, "plan", self.plan.id, "handoff", actor="alice")
        self.assertEqual(note.text, "handoff")
        self.assertEqual([n.text for n in services.list_notes(self.store, "plan", 1)], ["handoff"])

    def test_comment_resolution_and_mention(self) -> None:
        comment = services.add_comment(
            self.store, "plan", self.plan.id, "@bob please review", actor="alice"
        )
        self.assertEqual(
            [c.id for c in services.list_comments(self.store, "plan", 1, mentions="bob")],
            [comment.id],
        )
        resolved = services.resolve_comment(self.store, comment.id, resolved=True, actor="alice")
        assert resolved is not None
        self.assertTrue(resolved.resolved)


if __name__ == "__main__":
    unittest.main()
