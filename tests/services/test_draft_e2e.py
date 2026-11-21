"""End-to-end draft loop over a recipe-shaped plan document."""

from __future__ import annotations

import os
import tempfile
import unittest

from lazyplan.services import drafts, plan_recipes
from lazyplan.services.plan_document import validate_document
from lazyplan.store import Store


class DraftEndToEndTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(os.path.join(self.tmp.name, "t.db"))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    @staticmethod
    def _document() -> dict:
        raw = plan_recipes.load("feature")
        raw["plan"]["title"] = "Draft review end to end"
        raw["plan"]["why"] = "Prove the draft loop from add to promote."
        raw["plan"]["criteria"] = ["Draft promotes."]
        raw["milestones"][0]["criteria"] = ["Milestone lands."]
        raw["milestones"][0]["tasks"][0]["criteria"] = ["Implementation lands."]
        return raw

    def test_add_annotate_revise_respond_promote(self) -> None:
        raw = self._document()
        draft = drafts.create(self.store, raw, actor="agent")
        self.assertEqual(draft.title, "Draft review end to end")
        self.assertEqual(draft.status, "review")
        self.assertEqual(draft.revision, 1)
        self.assertEqual(self.store.counts()["plans"], 0)

        annotation = drafts.annotate(
            self.store,
            draft.id,
            "plan:why",
            "change",
            "Sharpen the why",
            quote="draft",
            author="human",
        )
        self.assertEqual(annotation.quote, "draft")
        self.assertEqual(self.store.get_draft(draft.id).status, "revising")

        revised = self._document()
        revised["plan"]["why"] = "A sharper proof of the draft loop."
        updated = drafts.revise(
            self.store,
            draft.id,
            revised,
            base_revision=1,
            actor="agent",
            note="Rewrote the why",
        )
        self.assertEqual(updated.revision, 2)
        self.assertEqual(updated.status, "review")
        moved = self.store.get_draft_annotation(annotation.id)
        assert moved is not None
        self.assertEqual(moved.anchor_state, "moved")
        self.assertEqual(moved.status, "open")

        answered = drafts.respond(
            self.store,
            annotation.id,
            "Rewrote the why",
            actor="agent",
        )
        self.assertEqual(answered.status, "addressed")
        self.assertEqual(drafts.ready(self.store, draft.id).status, "review")

        promotion = drafts.promote(self.store, draft.id, actor="agent")
        self.assertTrue(promotion.created)
        self.assertEqual(promotion.draft.status, "promoted")
        self.assertEqual(promotion.draft.plan_id, promotion.plan.id)
        self.assertEqual(self.store.counts()["plans"], 1)
        self._assert_tree(promotion.plan.id, revised)

        retry = drafts.promote(self.store, draft.id)
        self.assertFalse(retry.created)
        self.assertEqual(retry.plan.id, promotion.plan.id)

    def test_stale_revision_is_refused(self) -> None:
        draft = drafts.create(self.store, self._document(), actor="agent")
        with self.assertRaisesRegex(ValueError, "revision 1, not 0"):
            drafts.revise(self.store, draft.id, self._document(), base_revision=0)
        current = self.store.get_draft(draft.id)
        assert current is not None
        self.assertEqual(current.revision, 1)

    def test_open_annotation_blocks_promotion(self) -> None:
        draft = drafts.create(self.store, self._document(), actor="agent")
        drafts.annotate(self.store, draft.id, "plan:why", "change", "Sharpen")
        with self.assertRaisesRegex(ValueError, "open annotation"):
            drafts.promote(self.store, draft.id)
        self.assertEqual(self.store.counts()["plans"], 0)

    def _assert_tree(self, plan_id: int, raw: dict) -> None:
        expected = validate_document(self.store, raw)
        plan = self.store.get_plan(plan_id)
        assert plan is not None
        self.assertEqual(plan.name, expected.title)
        self.assertEqual(plan.goal, expected.why)
        self.assertEqual(plan.description, expected.what)
        self.assertEqual(
            [row.text for row in self.store.list_criteria("plan", plan_id)],
            list(expected.criteria),
        )
        milestones = self.store.list_milestones(plan_id)
        self.assertEqual(len(milestones), len(expected.milestones))
        for stored, wanted in zip(milestones, expected.milestones, strict=True):
            self.assertEqual(stored.title, wanted.title)
            self.assertEqual(stored.description, wanted.description)
            self.assertEqual(
                [row.text for row in self.store.list_criteria("milestone", stored.id)],
                list(wanted.criteria),
            )
            tasks = self.store.list_tasks(stored.id)
            self.assertEqual(len(tasks), len(wanted.tasks))
            for stored_task, wanted_task in zip(tasks, wanted.tasks, strict=True):
                self.assertEqual(stored_task.title, wanted_task.title)
                self.assertEqual(stored_task.description, wanted_task.description)
                self.assertEqual(stored_task.role, wanted_task.role)
                self.assertEqual(
                    [row.text for row in self.store.list_criteria("task", stored_task.id)],
                    list(wanted_task.criteria),
                )


if __name__ == "__main__":
    unittest.main()
