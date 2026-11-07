"""Ship note service over a real plan tree."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from lazyplan import services
from lazyplan.core.entities import Status
from lazyplan.services import ship
from lazyplan.store import Store


class TestShipService(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "t.db")
        self.plan = self.store.add_plan("P", "what", goal="why")
        milestone = self.store.add_milestone(self.plan.id, "M")
        done = self.store.add_task(milestone.id, "Done task")
        open_task = self.store.add_task(milestone.id, "Open task")
        services.set_status(self.store, "task", done.id, Status.DONE, actor="t")
        criterion = self.store.add_criteria("task", done.id, "Proof")
        self.store.add_evidence(criterion.id, command="pytest", exit_code=0)
        self.store.add_touchpoint(open_task.id, "src/store")
        self.store.link_commit("task", done.id, "a" * 40, subject="one")
        self.store.link_forge("task", done.id, 7, title="PR", state="merged", checks="pass")
        self.store.add_question(self.plan.id, "Which host?")
        self.store.add_note("plan", self.plan.id, "handoff", actor="ana")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_note_has_the_outcome_sections(self) -> None:
        note = ship.build(self.store, self.plan.id)
        assert note is not None
        self.assertEqual(note.payload["tasks"]["done"], 1)
        self.assertEqual(note.payload["tasks"]["total"], 2)
        self.assertEqual(note.payload["criteria"]["evidence"], 1)
        text = note.markdown
        for heading in ("## Why", "## What shipped", "## Evidence", "## Residual risks"):
            self.assertIn(heading, text)
        self.assertIn("T1 Done task", text)
        self.assertIn("T2 Open task", text)
        self.assertIn("Q", text)

    def test_missing_plan_returns_none(self) -> None:
        self.assertIsNone(ship.build(self.store, 999))

    def test_max_chars_is_respected(self) -> None:
        note = ship.build(self.store, self.plan.id, max_chars=500)
        assert note is not None
        self.assertLessEqual(len(note.markdown), 500)
        self.assertIn("## Why", note.markdown)


if __name__ == "__main__":
    unittest.main()
