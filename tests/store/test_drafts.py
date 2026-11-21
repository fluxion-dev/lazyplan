"""Store persistence for plan drafts, revisions, and annotations."""

from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from contextlib import closing

from lazyplan.store import Store
from lazyplan.store import migrate as migrate_mod


class TestDraftsStore(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "t.db")
        self.store = Store(self.db)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_schema_has_draft_tables_and_indexes(self) -> None:
        with closing(sqlite3.connect(self.db)) as conn:
            self.assertEqual(
                int(conn.execute("PRAGMA user_version").fetchone()[0]),
                migrate_mod.SCHEMA_VERSION,
            )
            tables = {
                str(row[0])
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            indexes = {
                str(row[0])
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")
            }
        for table in ("plan_drafts", "plan_draft_revisions", "draft_annotations"):
            self.assertIn(table, tables)
        for index in (
            "idx_plan_drafts_status",
            "idx_plan_draft_revisions_draft",
            "idx_draft_annotations_draft",
        ):
            self.assertIn(index, indexes)

    def test_v18_database_gains_draft_tables_without_losing_rows(self) -> None:
        plan = self.store.add_plan("Existing plan")
        with closing(sqlite3.connect(self.db)) as conn:
            conn.execute("DROP TABLE draft_annotations")
            conn.execute("DROP TABLE plan_draft_revisions")
            conn.execute("DROP TABLE plan_drafts")
            conn.execute("PRAGMA user_version = 18")
            conn.commit()

        reopened = Store(self.db)
        self.assertIsNotNone(reopened.get_plan(plan.id))
        draft = reopened.add_draft("Recovered draft", '{"plan": {}}', actor="planner")
        self.assertGreater(draft.id, 0)

    def test_add_get_and_list_drafts(self) -> None:
        first = self.store.add_draft("  First  ", "  {}  ", actor="planner", now=100.0)
        second = self.store.add_draft("Second", "{}", actor="planner")
        self.assertEqual(first.title, "First")
        self.assertEqual(first.document, "{}")
        self.assertEqual(first.status, "review")
        self.assertEqual(first.revision, 1)
        self.assertEqual(first.created_at, 100.0)
        self.assertEqual(self.store.get_draft(first.id), first)
        self.assertEqual([draft.id for draft in self.store.list_drafts()], [first.id, second.id])
        self.store.set_draft_status(second.id, "revising", actor="human")
        self.assertEqual([draft.id for draft in self.store.list_drafts("review")], [first.id])
        self.assertEqual([draft.id for draft in self.store.list_drafts("revising")], [second.id])
        with self.assertRaises(ValueError):
            self.store.list_drafts("bogus")

    def test_draft_format_defaults_and_round_trips(self) -> None:
        document = self.store.add_draft("Document", "{}")
        self.assertEqual(document.format, "document")
        sketch = self.store.add_draft("Sketch", "# Title\n", format="sketch")
        self.assertEqual(sketch.format, "sketch")
        updated, snapshot = self.store.add_draft_revision(
            sketch.id,
            "# Title\n\n## Why\nBecause.\n",
            format="sketch",
        )
        self.assertEqual((updated.format, snapshot.format), ("sketch", "sketch"))
        self.assertEqual(self.store.get_draft(sketch.id).format, "sketch")
        self.assertEqual(self.store.get_draft_revision(sketch.id, 2).format, "sketch")
        with self.assertRaises(ValueError):
            self.store.add_draft("Bogus", "{}", format="outline")

    def test_pre_format_drafts_migrate_to_document(self) -> None:
        old = os.path.join(self.tmp.name, "old.db")
        with closing(sqlite3.connect(old)) as conn:
            conn.executescript(
                """
                CREATE TABLE plan_drafts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'review',
                    document TEXT NOT NULL,
                    revision INTEGER NOT NULL DEFAULT 1,
                    actor TEXT NOT NULL DEFAULT 'human',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    plan_id INTEGER,
                    promoted_at REAL NOT NULL DEFAULT 0
                );
                CREATE TABLE plan_draft_revisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    draft_id INTEGER NOT NULL,
                    revision INTEGER NOT NULL,
                    document TEXT NOT NULL,
                    actor TEXT NOT NULL DEFAULT 'human',
                    ts REAL NOT NULL,
                    note TEXT NOT NULL DEFAULT ''
                );
                INSERT INTO plan_drafts
                    (title, document, created_at, updated_at)
                    VALUES ('Old draft', '{"plan": {}}', 1.0, 1.0);
                INSERT INTO plan_draft_revisions
                    (draft_id, revision, document, ts)
                    VALUES (1, 1, '{"plan": {}}', 1.0);
                PRAGMA user_version = 19;
                """
            )
            conn.commit()

        reopened = Store(old)
        draft = reopened.get_draft(1)
        assert draft is not None
        self.assertEqual(draft.format, "document")
        revision = reopened.get_draft_revision(1, 1)
        assert revision is not None
        self.assertEqual(revision.format, "document")

    def test_revision_snapshots_and_stale_base(self) -> None:
        draft = self.store.add_draft("Draft", '{"plan": {}}')
        updated, snapshot = self.store.add_draft_revision(
            draft.id,
            '{"plan": {"title": "Renamed"}}',
            actor="agent",
            note="  tighten why  ",
            title="Renamed draft",
            expected_revision=1,
            now=200.0,
        )
        self.assertEqual(updated.revision, 2)
        self.assertEqual(updated.title, "Renamed draft")
        self.assertEqual(updated.updated_at, 200.0)
        self.assertEqual(snapshot.revision, 2)
        self.assertEqual(snapshot.note, "tighten why")
        self.assertEqual(
            [row.revision for row in self.store.list_draft_revisions(draft.id)], [1, 2]
        )
        self.assertEqual(self.store.get_draft_revision(draft.id, 1).document, '{"plan": {}}')
        with self.assertRaises(ValueError):
            self.store.add_draft_revision(draft.id, "{}", expected_revision=1)
        with self.assertRaises(KeyError):
            self.store.add_draft_revision(999_999, "{}")

    def test_status_and_promotion_link(self) -> None:
        draft = self.store.add_draft("Draft", "{}")
        revising = self.store.set_draft_status(draft.id, "revising", actor="human")
        self.assertIsNotNone(revising)
        assert revising is not None
        self.assertEqual(revising.status, "revising")
        self.assertIsNone(self.store.set_draft_status(999_999, "review"))
        with self.assertRaises(ValueError):
            self.store.set_draft_status(draft.id, "bogus")

        plan = self.store.add_plan("Promoted plan")
        promoted = self.store.link_draft_plan(draft.id, plan.id, actor="agent")
        self.assertIsNotNone(promoted)
        assert promoted is not None
        self.assertEqual(promoted.status, "promoted")
        self.assertEqual(promoted.plan_id, plan.id)
        self.assertGreater(promoted.promoted_at, 0)
        with self.assertRaises(KeyError):
            self.store.link_draft_plan(draft.id, 999_999)

    def test_annotations_round_trip_and_counts(self) -> None:
        first_draft = self.store.add_draft("First", "{}")
        second_draft = self.store.add_draft("Second", "{}")
        first = self.store.add_draft_annotation(
            first_draft.id,
            "  plan:why  ",
            "comment",
            "  Tighten this  ",
            quote="this",
            start_offset=5,
            end_offset=9,
            author="human",
            now=300.0,
        )
        second = self.store.add_draft_annotation(
            first_draft.id, "plan:what", "question", "Why?", author="human"
        )
        self.assertEqual(first.block_key, "plan:why")
        self.assertEqual(first.body, "Tighten this")
        self.assertEqual(first.status, "open")
        self.assertEqual(first.anchor_state, "ok")
        self.assertEqual(first.revision, 1)
        self.assertEqual(self.store.draft_annotation_counts(first_draft.id), (2, 2))
        self.assertEqual(self.store.draft_annotation_counts(second_draft.id), (0, 0))
        self.assertEqual(
            self.store.draft_annotation_counts_map(),
            {first_draft.id: (2, 2)},
        )

        addressed = self.store.update_draft_annotation(
            first.id,
            actor="agent",
            status="addressed",
            response="Done",
            responded_by="agent",
            responded_at=400.0,
        )
        self.assertIsNotNone(addressed)
        assert addressed is not None
        self.assertEqual(addressed.status, "addressed")
        self.assertEqual(addressed.response, "Done")
        self.assertEqual(addressed.responded_by, "agent")
        self.assertEqual(addressed.responded_at, 400.0)
        self.assertEqual(self.store.draft_annotation_counts(first_draft.id), (1, 2))
        self.assertEqual(
            [row.id for row in self.store.list_draft_annotations(first_draft.id, "addressed")],
            [first.id],
        )

        moved = self.store.update_draft_annotation(
            first.id, anchor_state="moved", start_offset=10, end_offset=14
        )
        self.assertIsNotNone(moved)
        assert moved is not None
        self.assertEqual(moved.anchor_state, "moved")
        self.assertEqual(moved.start_offset, 10)
        self.assertEqual(moved.end_offset, 14)
        self.assertEqual(moved.status, "addressed")

        self.assertTrue(self.store.delete_draft_annotation(second.id))
        self.assertEqual(self.store.draft_annotation_counts(first_draft.id), (0, 1))

    def test_annotations_require_the_current_revision(self) -> None:
        draft = self.store.add_draft("Draft", "{}")
        self.store.add_draft_revision(draft.id, '{"next": true}')
        with self.assertRaises(ValueError):
            self.store.add_draft_annotation(draft.id, "plan:why", "comment", "Stale", revision=1)
        current = self.store.add_draft_annotation(
            draft.id, "plan:why", "change", "Current", revision=2
        )
        self.assertEqual(current.revision, 2)
        with self.assertRaises(KeyError):
            self.store.add_draft_annotation(999_999, "plan:why", "comment", "Missing")

    def test_annotation_validation(self) -> None:
        draft = self.store.add_draft("Draft", "{}")
        cases = (
            {"block_key": "  "},
            {"block_key": "plan:why", "kind": "bogus"},
            {"block_key": "plan:why", "body": "  "},
            {"block_key": "plan:why", "quote": "abc", "start_offset": 5, "end_offset": 5},
            {"block_key": "plan:why", "start_offset": -1},
        )
        for case in cases:
            with self.subTest(case=case), self.assertRaises(ValueError):
                self.store.add_draft_annotation(
                    draft.id,
                    case.get("block_key", "plan:why"),
                    case.get("kind", "comment"),
                    case.get("body", "Body"),
                    quote=case.get("quote", ""),
                    start_offset=case.get("start_offset", 0),
                    end_offset=case.get("end_offset", 0),
                )
        with self.assertRaises(ValueError):
            self.store.add_draft("   ", "{}")
        with self.assertRaises(ValueError):
            self.store.add_draft("Draft", "  ")
        with self.assertRaises(ValueError):
            self.store.add_draft("Draft", "{}", status="bogus")

    def test_delete_cascades_revisions_and_annotations(self) -> None:
        draft = self.store.add_draft("Draft", "{}")
        self.store.add_draft_revision(draft.id, '{"next": true}')
        self.store.add_draft_annotation(draft.id, "plan:why", "comment", "Body")
        self.assertTrue(self.store.delete_draft(draft.id, actor="human"))
        self.assertIsNone(self.store.get_draft(draft.id))
        self.assertEqual(self.store.list_draft_revisions(draft.id), [])
        self.assertEqual(self.store.list_draft_annotations(draft.id), [])
        self.assertFalse(self.store.delete_draft(draft.id))

    def test_draft_actions_reach_the_feed(self) -> None:
        draft = self.store.add_draft("Draft", "{}", actor="planner")
        self.store.add_draft_annotation(draft.id, "plan:why", "comment", "Body", author="human")
        event = self.store.feed(1)[0]
        self.assertEqual(event["actor"], "human")
        self.assertEqual(event["kind"], "draft")
        self.assertEqual(event["action"], "annotate")
        self.assertIn(f"D#{draft.id}", event["detail"])
