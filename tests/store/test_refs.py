"""Store persistence for external plan references."""

from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from contextlib import closing

from lazyplan.store import Store
from lazyplan.store import migrate as migrate_mod


class TestRefsStore(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "t.db")
        self.store = Store(self.db)
        self.plan = self.store.add_plan("Plan")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_schema_has_external_refs(self) -> None:
        with closing(sqlite3.connect(self.db)) as conn:
            self.assertEqual(
                int(conn.execute("PRAGMA user_version").fetchone()[0]),
                migrate_mod.SCHEMA_VERSION,
            )
            names = {
                str(row[0])
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")
            }
        self.assertIn("idx_external_refs_plan", names)

    def test_link_is_idempotent_and_updates_snapshot(self) -> None:
        first = self.store.link_ref(
            self.plan.id, "https://github.com/o/r/issues/7", title="Old", state="open"
        )
        second = self.store.link_ref(
            self.plan.id, "https://github.com/o/r/issues/7", title="New", state="closed"
        )
        self.assertEqual(first.id, second.id)
        self.assertEqual(second.provider, "github")
        self.assertEqual(second.kind, "issue")
        self.assertEqual(second.external_id, "7")
        self.assertEqual(second.title, "New")
        self.assertEqual(second.state, "closed")
        self.assertEqual(len(self.store.list_refs(self.plan.id)), 1)

    def test_unlink_by_id_and_url(self) -> None:
        first = self.store.link_ref(self.plan.id, "https://example.com/a")
        self.assertTrue(self.store.unlink_ref(self.plan.id, ref_id=first.id))
        self.assertFalse(self.store.unlink_ref(self.plan.id, ref_id=first.id))
        self.store.link_ref(self.plan.id, "https://example.com/b")
        self.assertTrue(self.store.unlink_ref(self.plan.id, url="https://example.com/b"))
        with self.assertRaises(ValueError):
            self.store.unlink_ref(self.plan.id)

    def test_plan_show_carries_refs_and_delete_cascades(self) -> None:
        self.store.link_ref(self.plan.id, "https://example.com/a", title="A")
        payload = self.store.get_full("plan", self.plan.id)
        assert payload is not None
        self.assertEqual(payload["refs"][0]["title"], "A")
        self.store.delete("plan", self.plan.id)
        self.assertEqual(self.store.list_refs(self.plan.id), [])

    def test_invalid_url_and_missing_plan(self) -> None:
        with self.assertRaises(ValueError):
            self.store.link_ref(self.plan.id, "ftp://example.com")
        with self.assertRaises(KeyError):
            self.store.link_ref(999, "https://example.com")

    def test_v7_database_gains_external_refs(self) -> None:
        path = os.path.join(self.tmp.name, "v7.db")
        with closing(sqlite3.connect(path)) as conn:
            conn.executescript(migrate_mod.SCHEMA)
            conn.execute("DROP TABLE external_refs")
            conn.execute("PRAGMA user_version = 7")
            conn.execute(
                "INSERT INTO plans (name, description, status, goal, uid)"
                " VALUES ('Old', '', 'todo', '', 'uid-old')"
            )
            conn.commit()
        store = Store(path)
        ref = store.link_ref(1, "https://example.com/a")
        self.assertEqual(ref.plan_id, 1)


if __name__ == "__main__":
    unittest.main()
