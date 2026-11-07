"""Approval and drift use cases."""

from __future__ import annotations

import os
import tempfile
import unittest

from lazyplan.core.entities import Status
from lazyplan.services import revisions as rev
from lazyplan.store import Store


class TestRevisionsService(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(os.path.join(self.tmp.name, "t.db"))
        self.plan = self.store.add_plan("Plan", description="what", goal="why")
        self.milestone = self.store.add_milestone(self.plan.id, "M")
        self.task = self.store.add_task(self.milestone.id, "T")
        self.store.set_entity_key("plan", self.plan.id, "plan-key")
        self.store.set_entity_key("task", self.task.id, "task-key")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_first_approval_and_noop(self) -> None:
        first = rev.approve(self.store, self.plan.id, actor="human", reason="initial")
        self.assertTrue(first.created)
        self.assertEqual(first.revision.revision, 1)
        self.assertEqual(first.acknowledged, 0)
        again = rev.approve(self.store, self.plan.id)
        self.assertFalse(again.created)
        self.assertEqual(again.revision.revision, 1)
        self.assertEqual(len(self.store.list_revisions(self.plan.id)), 1)

    def test_policy_change_creates_a_revision(self) -> None:
        rev.approve(self.store, self.plan.id)
        changed = rev.approve(self.store, self.plan.id, enforced=True)
        self.assertTrue(changed.created)
        self.assertEqual(changed.revision.revision, 2)
        self.assertTrue(changed.revision.enforced)
        self.assertEqual(changed.acknowledged, 0)

    def test_drift_needs_a_reason(self) -> None:
        rev.approve(self.store, self.plan.id)
        self.store.update_task(self.task.id, title="Renamed", reason="rename")
        with self.assertRaises(ValueError):
            rev.approve(self.store, self.plan.id)
        result = rev.approve(self.store, self.plan.id, reason="accept rename")
        self.assertTrue(result.created)
        self.assertEqual(result.revision.revision, 2)
        self.assertEqual(result.acknowledged, 1)

    def test_live_diff_attaches_reason(self) -> None:
        rev.approve(self.store, self.plan.id)
        self.store.update_task(self.task.id, title="Renamed", reason="rename")
        result = rev.diff(self.store, self.plan.id)
        self.assertTrue(result.drifted)
        self.assertEqual(result.summary["change"], 1)
        entry = result.entries[0]
        self.assertEqual(entry.change.kind, "task")
        self.assertEqual(entry.change.field, "title")
        self.assertEqual(entry.change.before, "T")
        self.assertEqual(entry.change.after, "Renamed")
        self.assertEqual(entry.reason, "rename")
        self.assertEqual(entry.actor, "human")

    def test_diff_is_clean_after_reapproval(self) -> None:
        rev.approve(self.store, self.plan.id)
        self.store.update_task(self.task.id, title="Renamed", reason="rename")
        rev.approve(self.store, self.plan.id, reason="accept rename")
        result = rev.diff(self.store, self.plan.id)
        self.assertFalse(result.drifted)
        self.assertEqual(result.entries, ())
        self.assertEqual(result.summary["total"], 0)

    def test_stored_revision_diff_has_no_reasons(self) -> None:
        rev.approve(self.store, self.plan.id)
        self.store.update_task(self.task.id, title="Renamed", reason="rename")
        rev.approve(self.store, self.plan.id, reason="accept rename")
        result = rev.diff(self.store, self.plan.id, from_revision=1, to_revision=2)
        self.assertTrue(result.drifted)
        self.assertEqual(result.entries[0].change.after, "Renamed")
        self.assertEqual(result.entries[0].reason, "")

    def test_diff_without_approval_raises(self) -> None:
        with self.assertRaises(ValueError):
            rev.diff(self.store, self.plan.id)

    def test_diff_unknown_revision_raises(self) -> None:
        rev.approve(self.store, self.plan.id)
        with self.assertRaises(ValueError):
            rev.diff(self.store, self.plan.id, from_revision=9)

    def test_revision_history_counts_changes(self) -> None:
        rev.approve(self.store, self.plan.id)
        self.store.update_task(self.task.id, title="Renamed", reason="rename")
        rev.approve(self.store, self.plan.id, reason="accept rename")
        history = rev.list_revisions(self.store, self.plan.id)
        self.assertEqual([item.revision.revision for item in history], [1, 2])
        self.assertEqual([item.changes for item in history], [0, 1])

    def test_drifted_plan_ids_and_state(self) -> None:
        rev.approve(self.store, self.plan.id)
        self.assertEqual(rev.drifted_plan_ids(self.store), set())
        self.store.update_task(self.task.id, title="Renamed", reason="rename")
        self.assertEqual(rev.drifted_plan_ids(self.store), {self.plan.id})
        self.assertEqual(rev.drift_counts(self.store), {self.plan.id: 1})
        state = rev.revision_state(self.store, self.plan.id)
        self.assertEqual(state["revision"], 1)
        self.assertEqual(state["drift"], 1)
        self.assertFalse(state["enforced"])

    def test_snapshot_uses_stable_keys(self) -> None:
        snap = rev.snapshot(self.store, self.plan.id)
        self.assertEqual(snap["plan"]["key"], "plan-key")
        self.assertEqual(snap["milestones"][0]["tasks"][0]["key"], "task-key")

    def test_status_and_ticks_do_not_create_drift(self) -> None:
        criterion = self.store.add_criteria("task", self.task.id, "proof")
        rev.approve(self.store, self.plan.id)
        self.store.set_status_raw("task", self.task.id, Status.DONE)
        self.store.set_criteria(criterion.id, True)
        self.assertFalse(rev.diff(self.store, self.plan.id).drifted)

    def test_done_gate_only_for_enforced_drift(self) -> None:
        rev.approve(self.store, self.plan.id)
        self.store.update_task(self.task.id, title="Renamed", reason="rename")
        self.assertIsNone(rev.done_gate(self.store, self.plan.id))
        rev.approve(self.store, self.plan.id, reason="accept rename", enforced=True)
        self.assertIsNone(rev.done_gate(self.store, self.plan.id))
        self.store.update_task(self.task.id, title="Renamed again", reason="rename again")
        failure = rev.done_gate(self.store, self.plan.id)
        self.assertIsNotNone(failure)
        assert failure is not None
        self.assertIn("scope change", failure)
        self.assertIn("plan diff", failure)

    def test_missing_plan_raises(self) -> None:
        with self.assertRaises(KeyError):
            rev.approve(self.store, 999_999)


if __name__ == "__main__":
    unittest.main()
