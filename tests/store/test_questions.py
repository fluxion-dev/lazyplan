"""Store persistence for plan questions."""

from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from contextlib import closing

from lazyplan.store import Store
from lazyplan.store import migrate as migrate_mod


class TestQuestionsStore(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "t.db")
        self.store = Store(self.db)
        self.plan = self.store.add_plan("Plan")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_schema_has_question_table_and_index(self) -> None:
        with closing(sqlite3.connect(self.db)) as conn:
            self.assertEqual(
                int(conn.execute("PRAGMA user_version").fetchone()[0]),
                migrate_mod.SCHEMA_VERSION,
            )
            names = {
                str(row[0])
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")
            }
        self.assertIn("idx_plan_questions_plan", names)

    def test_add_list_and_filter(self) -> None:
        first = self.store.add_question(self.plan.id, "  Which host?  ", actor="qa")
        second = self.store.add_question(self.plan.id, "Which team?")
        self.assertEqual(first.text, "Which host?")
        self.assertEqual(first.actor, "qa")
        self.assertEqual(
            [row.id for row in self.store.list_questions(self.plan.id)], [first.id, second.id]
        )
        self.store.resolve_question(second.id, "solo", actor="human")
        self.assertEqual([row.id for row in self.store.list_questions(self.plan.id)], [first.id])
        self.assertEqual(
            [row.id for row in self.store.list_questions(self.plan.id, status="resolved")],
            [second.id],
        )
        self.assertEqual(len(self.store.list_questions(self.plan.id, status="all")), 2)

    def test_duplicate_open_question_is_rejected(self) -> None:
        self.store.add_question(self.plan.id, "Which host?")
        with self.assertRaises(ValueError):
            self.store.add_question(self.plan.id, "Which host?")
        first = self.store.list_questions(self.plan.id)[0]
        self.store.resolve_question(first.id)
        second = self.store.add_question(self.plan.id, "Which host?")
        self.assertNotEqual(second.id, first.id)

    def test_resolve_and_reopen(self) -> None:
        question = self.store.add_question(self.plan.id, "Which host?")
        resolved = self.store.resolve_question(question.id, "OpenCode first", actor="human")
        assert resolved is not None
        self.assertEqual(resolved.status, "resolved")
        self.assertEqual(resolved.resolution, "OpenCode first")
        self.assertEqual(resolved.resolved_by, "human")
        self.assertGreater(resolved.resolved_at, 0)
        reopened = self.store.reopen_question(question.id, "host choice changed", actor="human")
        assert reopened is not None
        self.assertEqual(reopened.status, "open")
        self.assertEqual(reopened.resolution, "")
        notes = self.store.list_notes("plan", self.plan.id)
        self.assertTrue(any("host choice changed" in note.text for note in notes))

    def test_missing_plan_is_rejected(self) -> None:
        with self.assertRaises(KeyError):
            self.store.add_question(999_999, "Why?")

    def test_plan_payload_includes_questions(self) -> None:
        question = self.store.add_question(self.plan.id, "Which host?")
        full = self.store.get_full("plan", self.plan.id)
        assert full is not None
        self.assertEqual(full["questions"][0]["id"], question.id)

    def test_questions_map(self) -> None:
        question = self.store.add_question(self.plan.id, "Which host?")
        self.assertEqual(self.store.questions_map()[self.plan.id][0].id, question.id)

    def test_plan_delete_cascades_questions(self) -> None:
        self.store.add_question(self.plan.id, "Which host?")
        self.store.delete("plan", self.plan.id)
        self.assertEqual(self.store.list_questions(self.plan.id, status="all"), [])

    def test_v4_database_gains_question_table(self) -> None:
        path = os.path.join(self.tmp.name, "v4.db")
        with closing(sqlite3.connect(path)) as conn:
            conn.executescript(migrate_mod.SCHEMA)
            conn.execute("DROP TABLE plan_questions")
            conn.execute("PRAGMA user_version = 4")
            conn.execute(
                "INSERT INTO plans (name, description, status, goal, uid)"
                " VALUES ('Old', '', 'todo', '', 'uid-old')"
            )
            conn.commit()
        store = Store(path)
        plan = store.list_plans()[0]
        self.assertEqual(store.add_question(plan.id, "Why?").text, "Why?")


if __name__ == "__main__":
    unittest.main()
