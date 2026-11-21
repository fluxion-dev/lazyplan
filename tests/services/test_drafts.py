"""Draft use cases: validation, revisions, annotations, and promotion."""

from __future__ import annotations

import json
import os
import tempfile
import unittest

from lazyplan.services import drafts
from lazyplan.store import Store


def document(
    key: str = "demo-plan",
    title: str = "Demo plan",
    why: str = "Why this matters.",
    what: str = "## Scope\n\n- One thing.",
) -> dict:
    return {
        "plan": {
            "key": key,
            "title": title,
            "why": why,
            "what": what,
            "criteria": ["Works."],
        },
        "milestones": [
            {
                "key": "build",
                "title": "Build it",
                "desc": "As a user, I want the change.",
                "criteria": ["Built."],
                "tasks": [
                    {
                        "key": "impl",
                        "title": "Implement it",
                        "desc": "Approach: do the work.",
                        "criteria": ["Tests pass."],
                    }
                ],
            }
        ],
    }


def minimal_document(why: str = "Why this matters.") -> dict:
    return {
        "plan": {
            "key": "demo-plan",
            "title": "Demo plan",
            "why": why,
            "what": "## Scope\n\n- One thing.",
        }
    }


SKETCH = (
    "# Sketch title\n\n## Why\n\nBecause review should stay at the definition."
    "\n\n## What\n\n## Scope\n\n- One thing.\n\n## Done\n\n- Works."
)


class DraftsServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(os.path.join(self.tmp.name, "t.db"))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_create_normalizes_and_lists(self) -> None:
        draft = drafts.create(self.store, document(), actor="planner")
        self.assertEqual(draft.title, "Demo plan")
        self.assertEqual(draft.status, "review")
        self.assertEqual(draft.revision, 1)
        self.assertEqual(draft.actor, "planner")
        payload = json.loads(draft.document)
        self.assertEqual(payload["plan"]["key"], "demo-plan")
        self.assertEqual(payload["plan"]["dispatch_mode"], "serial")
        self.assertEqual(payload["milestones"][0]["tasks"][0]["key"], "impl")
        self.assertEqual([row.id for row in drafts.list_drafts(self.store)], [draft.id])
        self.assertEqual(drafts.list_drafts(self.store, "review"), [draft])

    def test_create_refuses_an_existing_plan_key(self) -> None:
        plan = self.store.add_plan("Existing")
        self.store.set_entity_key("plan", plan.id, "demo-plan")
        with self.assertRaisesRegex(ValueError, "already belongs to plan"):
            drafts.create(self.store, document())

    def test_detail_exposes_blocks_and_counts(self) -> None:
        draft = drafts.create(self.store, document())
        detail = drafts.detail(self.store, draft.id)
        self.assertEqual(detail.draft, draft)
        self.assertEqual(detail.blocks[0].key, "plan:title")
        self.assertIn("plan:why", {block.key for block in detail.blocks})
        self.assertEqual((detail.open_annotations, detail.total_annotations), (0, 0))
        with self.assertRaises(KeyError):
            drafts.detail(self.store, 999_999)

    def test_sketch_detail_blocks_and_annotation(self) -> None:
        draft = self.store.add_draft("Sketch title", SKETCH, format="sketch")
        detail = drafts.detail(self.store, draft.id)
        self.assertIsNone(detail.document)
        assert detail.sketch is not None
        self.assertEqual(detail.sketch.title, "Sketch title")
        self.assertEqual(
            [block.key for block in detail.blocks],
            ["sketch:title", "sketch:why", "sketch:what", "sketch:criterion:0"],
        )
        annotation = drafts.annotate(
            self.store,
            draft.id,
            "sketch:why",
            "change",
            "Sharpen this",
            quote="review",
            author="human",
        )
        self.assertEqual((annotation.start_offset, annotation.end_offset), (8, 14))
        self.assertEqual(self.store.get_draft(draft.id).status, "revising")

    def test_sketch_does_not_reserve_a_plan_key(self) -> None:
        self.store.add_draft("Sketch title", SKETCH, format="sketch")
        draft = drafts.create(self.store, document())
        self.assertEqual(json.loads(draft.document)["plan"]["key"], "demo-plan")

    def test_unreadable_sketch_is_named(self) -> None:
        draft = self.store.add_draft("Broken", "# No sections", format="sketch")
        with self.assertRaisesRegex(ValueError, "unreadable sketch"):
            drafts.detail(self.store, draft.id)
        with self.assertRaisesRegex(ValueError, "unreadable sketch"):
            drafts.annotate(self.store, draft.id, "sketch:why", "comment", "No")

    def test_annotate_stores_a_quote_and_offsets(self) -> None:
        draft = drafts.create(self.store, document())
        annotation = drafts.annotate(
            self.store,
            draft.id,
            "plan:why",
            "comment",
            "  Tighten this  ",
            quote="Why",
            author="human",
        )
        self.assertEqual(annotation.body, "Tighten this")
        self.assertEqual(annotation.quote, "Why")
        self.assertEqual((annotation.start_offset, annotation.end_offset), (0, 3))
        self.assertEqual(annotation.status, "open")
        self.assertEqual(annotation.revision, 1)
        block_level = drafts.annotate(
            self.store, draft.id, "plan:what", "change", "Restructure", quote=""
        )
        self.assertEqual((block_level.start_offset, block_level.end_offset), (0, 0))
        detail = drafts.detail(self.store, draft.id)
        self.assertEqual((detail.open_annotations, detail.total_annotations), (2, 2))

    def test_annotate_resolves_duplicate_quotes_with_offsets(self) -> None:
        draft = drafts.create(self.store, document(why="same same"))
        with self.assertRaisesRegex(ValueError, "more than once"):
            drafts.annotate(self.store, draft.id, "plan:why", "comment", "Ambiguous", quote="same")
        second = drafts.annotate(
            self.store,
            draft.id,
            "plan:why",
            "comment",
            "Second one",
            quote="same",
            start_offset=5,
            end_offset=9,
        )
        self.assertEqual((second.start_offset, second.end_offset), (5, 9))

    def test_annotate_rejects_unknown_blocks_and_quotes(self) -> None:
        draft = drafts.create(self.store, document())
        with self.assertRaisesRegex(ValueError, "not found in draft"):
            drafts.annotate(self.store, draft.id, "missing:block", "comment", "Body")
        with self.assertRaisesRegex(ValueError, "was not found"):
            drafts.annotate(self.store, draft.id, "plan:why", "comment", "Body", quote="absent")
        with self.assertRaises(KeyError):
            drafts.annotate(self.store, 999_999, "plan:why", "comment", "Body")

    def test_create_keeps_the_plan_queue_empty(self) -> None:
        drafts.create(self.store, document())
        self.assertEqual(self.store.counts()["plans"], 0)
        self.assertEqual(self.store.list_plans(), [])

    def test_invalid_revision_does_not_write_a_snapshot(self) -> None:
        draft = drafts.create(self.store, document())
        with self.assertRaises(ValueError):
            drafts.revise(
                self.store,
                draft.id,
                {"plan": {"key": "demo-plan"}},
                base_revision=1,
            )
        current = self.store.get_draft(draft.id)
        self.assertIsNotNone(current)
        assert current is not None
        self.assertEqual(current.revision, 1)
        self.assertEqual(len(self.store.list_draft_revisions(draft.id)), 1)

    def test_failed_promotion_creates_no_plan(self) -> None:
        draft = drafts.create(self.store, document())
        drafts.annotate(self.store, draft.id, "plan:why", "change", "Sharpen")
        with self.assertRaisesRegex(ValueError, "open annotation"):
            drafts.promote(self.store, draft.id)
        self.assertEqual(self.store.counts()["plans"], 0)

    def test_revise_requires_the_base_and_returns_to_review(self) -> None:
        draft = drafts.create(self.store, document())
        annotation = drafts.annotate(self.store, draft.id, "plan:why", "change", "Sharpen this")
        self.assertEqual(self.store.get_draft(draft.id).status, "revising")
        with self.assertRaisesRegex(ValueError, "revision 1, not 0"):
            drafts.revise(self.store, draft.id, document(), base_revision=0)
        revised = drafts.revise(
            self.store,
            draft.id,
            document(title="Revised", why="A sharper why."),
            base_revision=1,
            actor="agent",
            note="  addressed  ",
        )
        self.assertEqual(revised.revision, 2)
        self.assertEqual(revised.status, "review")
        self.assertEqual(revised.title, "Revised")
        snapshot = self.store.get_draft_revision(draft.id, 2)
        self.assertIsNotNone(snapshot)
        assert snapshot is not None
        self.assertEqual(snapshot.note, "addressed")
        self.assertEqual(
            [row.status for row in drafts.list_annotations(self.store, draft.id)], ["open"]
        )
        with self.assertRaisesRegex(ValueError, "revision 2, not 1"):
            drafts.revise(self.store, draft.id, document(), base_revision=1)
        with self.assertRaises(KeyError):
            drafts.revise(self.store, 999_999, document(), base_revision=1)
        self.assertEqual(annotation.draft_id, draft.id)

    def test_revise_reanchors_exact_moved_and_lost_quotes(self) -> None:
        draft = drafts.create(self.store, document())
        exact = drafts.annotate(self.store, draft.id, "plan:title", "comment", "Keep", quote="Demo")
        moved = drafts.annotate(self.store, draft.id, "plan:why", "change", "Move", quote="matters")
        lost = drafts.annotate(
            self.store, draft.id, "plan:what", "change", "Gone", quote="One thing"
        )
        drafts.revise(
            self.store,
            draft.id,
            document(
                why="A new why this matters.",
                what="## Scope\n\n- Only this.",
            ),
            base_revision=1,
            actor="agent",
        )
        rows = {row.id: row for row in drafts.list_annotations(self.store, draft.id)}
        self.assertEqual(rows[exact.id].anchor_state, "ok")
        self.assertEqual((rows[exact.id].start_offset, rows[exact.id].end_offset), (0, 4))
        self.assertEqual(rows[moved.id].anchor_state, "moved")
        self.assertEqual((rows[moved.id].start_offset, rows[moved.id].end_offset), (15, 22))
        self.assertEqual(rows[lost.id].anchor_state, "orphaned")
        self.assertEqual((rows[lost.id].start_offset, rows[lost.id].end_offset), (12, 21))
        self.assertEqual({row.status for row in rows.values()}, {"open"})

    def test_revise_reanchors_duplicates_and_recovers(self) -> None:
        draft = drafts.create(self.store, document(why="same same"))
        annotation = drafts.annotate(
            self.store,
            draft.id,
            "plan:why",
            "comment",
            "Second copy",
            quote="same",
            start_offset=5,
            end_offset=9,
        )
        self.assertEqual(annotation.anchor_state, "ok")
        drafts.revise(
            self.store,
            draft.id,
            document(why="same same"),
            base_revision=1,
            actor="agent",
        )
        orphaned = drafts.list_annotations(self.store, draft.id)[0]
        self.assertEqual(orphaned.anchor_state, "orphaned")
        self.assertEqual((orphaned.start_offset, orphaned.end_offset), (5, 9))
        drafts.revise(
            self.store,
            draft.id,
            document(why="same only"),
            base_revision=2,
            actor="agent",
        )
        moved = drafts.list_annotations(self.store, draft.id)[0]
        self.assertEqual(moved.anchor_state, "moved")
        self.assertEqual((moved.start_offset, moved.end_offset), (0, 4))

    def test_revise_orphans_annotations_on_removed_blocks(self) -> None:
        draft = drafts.create(self.store, document())
        task_annotation = drafts.annotate(
            self.store, draft.id, "task:impl", "comment", "Keep the task"
        )
        why_annotation = drafts.annotate(
            self.store, draft.id, "plan:why", "comment", "Keep the why", quote="Why"
        )
        drafts.revise(
            self.store,
            draft.id,
            minimal_document(),
            base_revision=1,
            actor="agent",
        )
        rows = {row.id: row for row in drafts.list_annotations(self.store, draft.id)}
        self.assertEqual(rows[task_annotation.id].anchor_state, "orphaned")
        self.assertEqual(rows[why_annotation.id].anchor_state, "ok")
        self.assertEqual(
            (rows[why_annotation.id].start_offset, rows[why_annotation.id].end_offset),
            (0, 3),
        )

    def test_dismissed_annotations_are_not_reanchored(self) -> None:
        draft = drafts.create(self.store, document())
        dismissed = drafts.annotate(
            self.store, draft.id, "plan:why", "comment", "Old", quote="matters"
        )
        drafts.dismiss(self.store, dismissed.id, "no longer relevant")
        drafts.annotate(self.store, draft.id, "plan:what", "comment", "Keep")
        drafts.revise(
            self.store,
            draft.id,
            document(why="Because."),
            base_revision=1,
            actor="agent",
        )
        row = self.store.get_draft_annotation(dismissed.id)
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row.status, "dismissed")
        self.assertEqual(row.anchor_state, "ok")
        self.assertEqual((row.start_offset, row.end_offset), (9, 16))

    def test_annotate_moves_to_revising_then_ready_and_resolve(self) -> None:
        draft = drafts.create(self.store, document())
        self.assertEqual(draft.status, "review")
        annotation = drafts.annotate(self.store, draft.id, "plan:why", "question", "Why?")
        self.assertEqual(self.store.get_draft(draft.id).status, "revising")
        with self.assertRaisesRegex(ValueError, "still has 1 open"):
            drafts.ready(self.store, draft.id)
        resolved = drafts.resolve(self.store, annotation.id, "Because", actor="agent", now=100.0)
        self.assertEqual(resolved.status, "addressed")
        self.assertEqual(resolved.response, "Because")
        self.assertEqual(resolved.responded_by, "agent")
        self.assertEqual(resolved.responded_at, 100.0)
        self.assertEqual(drafts.ready(self.store, draft.id).status, "review")
        self.assertEqual(drafts.ready(self.store, draft.id).status, "review")

    def test_respond_dismiss_and_delete(self) -> None:
        draft = drafts.create(self.store, document())
        question = drafts.annotate(self.store, draft.id, "plan:why", "question", "Why?")
        with self.assertRaisesRegex(ValueError, "must not be empty"):
            drafts.respond(self.store, question.id, "  ")
        answered = drafts.respond(self.store, question.id, "Because", actor="agent", now=100.0)
        self.assertEqual(answered.status, "addressed")
        self.assertEqual(answered.response, "Because")
        change = drafts.annotate(self.store, draft.id, "plan:what", "change", "Shorten it")
        dismissed = drafts.dismiss(self.store, change.id, "wontfix", actor="human", now=200.0)
        self.assertEqual(dismissed.status, "dismissed")
        self.assertEqual(dismissed.response, "wontfix")
        with self.assertRaisesRegex(ValueError, "is dismissed"):
            drafts.respond(self.store, change.id, "late")
        self.assertEqual(drafts.dismiss(self.store, change.id), dismissed)
        self.assertTrue(drafts.delete_annotation(self.store, question.id, actor="human"))
        self.assertIsNone(self.store.get_draft_annotation(question.id))
        with self.assertRaises(KeyError):
            drafts.delete_annotation(self.store, question.id)

    def test_promote_gates_and_creates_the_tree(self) -> None:
        draft = drafts.create(self.store, document())
        annotation = drafts.annotate(self.store, draft.id, "plan:why", "change", "Sharpen")
        with self.assertRaisesRegex(ValueError, "open annotation"):
            drafts.promote(self.store, draft.id)
        drafts.resolve(self.store, annotation.id, "Done", actor="agent")
        with self.assertRaisesRegex(ValueError, "revising"):
            drafts.promote(self.store, draft.id)
        drafts.ready(self.store, draft.id)
        promotion = drafts.promote(self.store, draft.id, actor="agent")
        self.assertTrue(promotion.created)
        self.assertEqual(promotion.plan.name, "Demo plan")
        self.assertEqual(promotion.counts, {"milestones": 1, "tasks": 1, "criteria": 3})
        self.assertEqual(promotion.draft.status, "promoted")
        self.assertEqual(promotion.draft.plan_id, promotion.plan.id)
        milestones = self.store.list_milestones(promotion.plan.id)
        self.assertEqual([row.title for row in milestones], ["Build it"])
        tasks = self.store.list_tasks(milestones[0].id)
        self.assertEqual([row.title for row in tasks], ["Implement it"])
        retry = drafts.promote(self.store, draft.id)
        self.assertFalse(retry.created)
        self.assertEqual(retry.plan.id, promotion.plan.id)

    def test_promote_refuses_a_taken_plan_key(self) -> None:
        draft = drafts.create(self.store, document())
        existing = self.store.add_plan("Existing")
        self.store.set_entity_key("plan", existing.id, "demo-plan")
        with self.assertRaisesRegex(ValueError, "already belongs to plan"):
            drafts.promote(self.store, draft.id)

    def test_annotating_a_revising_draft_keeps_it_revising(self) -> None:
        draft = drafts.create(self.store, document())
        drafts.annotate(self.store, draft.id, "plan:why", "change", "One")
        drafts.annotate(self.store, draft.id, "plan:what", "comment", "Two")
        self.assertEqual(self.store.get_draft(draft.id).status, "revising")

    def _wait(self, draft_id: int, timeout: float | None = 1.0) -> drafts.DraftWake | None:
        ticks = iter(range(100))
        return drafts.wait_for_feedback(
            self.store,
            draft_id,
            timeout=timeout,
            clock=lambda: float(next(ticks)),
            sleep=lambda _seconds: None,
        )

    def test_wait_returns_open_feedback_at_once(self) -> None:
        draft = drafts.create(self.store, document())
        annotation = drafts.annotate(self.store, draft.id, "plan:why", "change", "Sharpen")
        wake = self._wait(draft.id)
        assert wake is not None
        self.assertEqual([row.id for row in wake.annotations], [annotation.id])
        self.assertEqual(wake.draft.status, "revising")

    def test_wait_ignores_addressed_and_dismissed_feedback(self) -> None:
        draft = drafts.create(self.store, document())
        first = drafts.annotate(self.store, draft.id, "plan:why", "change", "One")
        second = drafts.annotate(self.store, draft.id, "plan:what", "comment", "Two")
        drafts.respond(self.store, first.id, "Done")
        drafts.dismiss(self.store, second.id, "No")
        self.assertIsNone(self._wait(draft.id, timeout=3.0))

    def test_wait_times_out_without_feedback(self) -> None:
        draft = drafts.create(self.store, document())
        self.assertIsNone(self._wait(draft.id, timeout=3.0))

    def test_wait_ends_with_no_feedback_once_promoted(self) -> None:
        draft = drafts.create(self.store, document())
        drafts.promote(self.store, draft.id)
        wake = self._wait(draft.id)
        assert wake is not None
        self.assertEqual(wake.draft.status, "promoted")
        self.assertEqual(wake.annotations, ())

    def test_wait_names_a_missing_draft(self) -> None:
        with self.assertRaisesRegex(KeyError, "draft #9 not found"):
            self._wait(9)

    def test_promoted_draft_is_read_only(self) -> None:
        draft = drafts.create(self.store, document())
        annotation = drafts.annotate(self.store, draft.id, "plan:why", "comment", "Body")
        drafts.resolve(self.store, annotation.id, "Done")
        drafts.ready(self.store, draft.id)
        drafts.promote(self.store, draft.id)
        with self.assertRaisesRegex(ValueError, "read-only"):
            drafts.annotate(self.store, draft.id, "plan:why", "comment", "Late")
        with self.assertRaisesRegex(ValueError, "read-only"):
            drafts.delete_annotation(self.store, annotation.id)
        with self.assertRaisesRegex(ValueError, "promoted"):
            drafts.revise(self.store, draft.id, document(), base_revision=1)
        with self.assertRaisesRegex(ValueError, "promoted"):
            drafts.ready(self.store, draft.id)
        with self.assertRaisesRegex(ValueError, "promoted"):
            drafts.delete_draft(self.store, draft.id)
