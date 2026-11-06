"""Store persistence for approvals and the scope-change ledger."""

from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from contextlib import closing

from lazyplan.core.entities import Status
from lazyplan.store import Store
from lazyplan.store import migrate as migrate_mod


class TestRevisionsStore(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "t.db")
        self.store = Store(self.db)
        self.plan = self.store.add_plan("Plan")
        self.milestone = self.store.add_milestone(self.plan.id, "M")
        self.task = self.store.add_task(self.milestone.id, "T")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def approve(self, reason: str = "initial") -> int:
        revision = self.store.add_revision(
            self.plan.id,
            "a" * 64,
            "{}",
            reason=reason,
            change_mark=self.store.max_change_id(self.plan.id),
        )
        return revision.revision

    def test_schema_has_revision_tables_and_indexes(self) -> None:
        with closing(sqlite3.connect(self.db)) as conn:
            self.assertEqual(
                int(conn.execute("PRAGMA user_version").fetchone()[0]),
                migrate_mod.SCHEMA_VERSION,
            )
            names = {
                str(row[0])
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")
            }
        self.assertIn("idx_plan_revisions_plan", names)
        self.assertIn("idx_plan_changes_plan", names)

    def test_revision_numbering_and_latest(self) -> None:
        self.assertEqual(self.approve("first"), 1)
        self.assertEqual(self.approve("second"), 2)
        latest = self.store.latest_revision(self.plan.id)
        self.assertIsNotNone(latest)
        assert latest is not None
        self.assertEqual(latest.revision, 2)
        self.assertEqual(latest.reason, "second")
        self.assertEqual(
            [item.revision for item in self.store.list_revisions(self.plan.id)], [1, 2]
        )
        self.assertEqual(self.store.latest_revisions_map()[self.plan.id].revision, 2)

    def test_no_changes_before_approval(self) -> None:
        self.store.update_task(self.task.id, title="Renamed", reason="scope")
        self.store.add_criteria("task", self.task.id, "proof", reason="scope")
        self.assertEqual(self.store.list_plan_changes(self.plan.id), [])

    def test_scope_changes_are_recorded_with_reasons(self) -> None:
        self.approve()
        self.store.update_plan(self.plan.id, description="new what", reason="narrow scope")
        self.store.update_milestone(self.milestone.id, title="M2", reason="rename")
        self.store.update_task(self.task.id, description="new desc", reason="clarify")
        added = self.store.add_milestone(self.plan.id, "M3", reason="new slice")
        task = self.store.add_task(added.id, "T3", reason="new work")
        criterion = self.store.add_criteria("task", task.id, "proves T3", reason="proof")
        self.store.delete_criteria(criterion.id, reason="wrong proof")
        self.store.delete("task", task.id, reason="not needed")
        self.store.delete("milestone", added.id, reason="not needed")

        changes = self.store.list_plan_changes(self.plan.id)
        pairs = [(item.kind, item.action, item.field, item.reason) for item in changes]
        self.assertIn(("plan", "edit", "what", "narrow scope"), pairs)
        self.assertIn(("milestone", "edit", "title", "rename"), pairs)
        self.assertIn(("task", "edit", "desc", "clarify"), pairs)
        self.assertIn(("milestone", "add", "", "new slice"), pairs)
        self.assertIn(("task", "add", "", "new work"), pairs)
        self.assertIn(("criterion", "add", "", "proof"), pairs)
        self.assertIn(("criterion", "delete", "", "wrong proof"), pairs)
        self.assertIn(("task", "delete", "", "not needed"), pairs)
        self.assertIn(("milestone", "delete", "", "not needed"), pairs)

    def test_status_tick_claim_and_links_are_not_scope(self) -> None:
        criterion = self.store.add_criteria("task", self.task.id, "proof")
        self.approve()
        self.store.claim_task(self.task.id, "actor")
        self.store.set_status_raw("task", self.task.id, Status.DONE)
        self.store.set_criteria(criterion.id, True)
        self.assertEqual(self.store.list_plan_changes(self.plan.id), [])

    def test_drift_counts_and_reapproval(self) -> None:
        self.approve()
        self.store.update_task(self.task.id, title="Renamed", reason="rename")
        self.store.add_criteria("task", self.task.id, "extra", reason="extra")
        self.assertEqual(self.store.plan_drift(self.plan.id), 2)
        self.assertEqual(self.store.drift_counts().get(self.plan.id), 2)
        self.approve("reapproved")
        self.assertEqual(self.store.plan_drift(self.plan.id), 0)
        self.assertEqual(self.store.drift_counts(), {})

    def test_change_mark_ignores_older_changes(self) -> None:
        self.approve()
        self.store.update_task(self.task.id, title="Renamed", reason="rename")
        mark = self.store.max_change_id(self.plan.id)
        self.store.add_revision(self.plan.id, "b" * 64, "{}", reason="reapproved", change_mark=mark)
        self.store.update_task(self.task.id, description="new desc", reason="clarify")
        changes = self.store.list_plan_changes(self.plan.id, after_id=mark)
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].field, "desc")

    def test_plan_delete_cascades_revisions_and_changes(self) -> None:
        self.approve()
        self.store.update_task(self.task.id, title="Renamed", reason="rename")
        self.store.delete("plan", self.plan.id, reason="abandoned")
        self.assertIsNone(self.store.latest_revision(self.plan.id))
        self.assertEqual(self.store.list_plan_changes(self.plan.id), [])

    def test_plan_for_kind_resolves_each_level(self) -> None:
        criterion = self.store.add_criteria("task", self.task.id, "proof")
        self.assertEqual(self.store._plan_for_kind("plan", self.plan.id), self.plan.id)
        self.assertEqual(self.store._plan_for_kind("milestone", self.milestone.id), self.plan.id)
        self.assertEqual(self.store._plan_for_kind("task", self.task.id), self.plan.id)
        self.assertEqual(self.store._plan_for_kind("criterion", criterion.id), self.plan.id)
        self.assertIsNone(self.store._plan_for_kind("task", 999_999))

    def test_entity_keys_map(self) -> None:
        self.store.set_entity_key("plan", self.plan.id, "plan-key")
        self.store.set_entity_key("milestone", self.milestone.id, "m-key")
        keys = self.store.entity_keys_map()
        self.assertEqual(keys[("plan", self.plan.id)], "plan-key")
        self.assertEqual(keys[("milestone", self.milestone.id)], "m-key")

    def test_transaction_rolls_back_change_rows(self) -> None:
        self.approve()
        with self.assertRaises(RuntimeError):
            with self.store.transaction():
                self.store.update_task(self.task.id, title="Renamed", reason="rename")
                raise RuntimeError("boom")
        self.assertEqual(self.store.list_plan_changes(self.plan.id), [])

    def test_v2_database_gains_revision_tables(self) -> None:
        path = os.path.join(self.tmp.name, "v2.db")
        with closing(sqlite3.connect(path)) as conn:
            conn.executescript(migrate_mod.SCHEMA)
            conn.execute("DROP TABLE plan_revisions")
            conn.execute("DROP TABLE plan_changes")
            conn.execute("PRAGMA user_version = 2")
            conn.execute(
                "INSERT INTO plans (name, description, status, goal, uid)"
                " VALUES ('Old', '', 'todo', '', 'uid-old')"
            )
            conn.commit()
        store = Store(path)
        self.assertEqual(store.list_plans()[0].name, "Old")
        revision = store.add_revision(store.list_plans()[0].id, "c" * 64, "{}")
        self.assertEqual(revision.revision, 1)

    def test_change_rows_roll_back_with_the_write(self) -> None:
        self.approve()

        def fail(*_args: object, **_kwargs: object) -> None:
            raise RuntimeError("boom")

        with self.assertRaises(RuntimeError):
            with self.store.transaction():
                self.store.add_plan_change(
                    self.plan.id, "task", self.task.id, "edit", field="title"
                )
                fail()
        self.assertEqual(self.store.list_plan_changes(self.plan.id), [])


if __name__ == "__main__":
    unittest.main()
