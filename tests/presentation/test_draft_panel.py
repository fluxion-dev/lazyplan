"""The main-screen plan drafts panel: rows, selection, and guards."""

from __future__ import annotations

import os
import tempfile
import unittest

from lazyplan.presentation.shared import registry
from lazyplan.services import drafts
from lazyplan.store import Store

try:
    from textual.geometry import Offset
    from textual.selection import Selection
    from textual.widgets import Button, Input, OptionList, Select, TextArea

    _TEXTUAL_OK = True
except ImportError:  # pragma: no cover - textual not installed
    Offset = None  # type: ignore[assignment]
    Selection = None  # type: ignore[assignment]
    Button = Input = OptionList = Select = TextArea = None  # type: ignore[assignment,misc]
    _TEXTUAL_OK = False

try:
    from lazyplan.presentation.tui import create_app
except ImportError:  # pragma: no cover - textual not installed
    create_app = None  # type: ignore[assignment]


def document(why: str = "Why this matters.") -> dict:
    return {
        "plan": {
            "key": "demo-plan",
            "title": "Demo plan",
            "why": why,
            "what": "## Scope\n\n- One thing.",
            "criteria": ["Works."],
        },
        "milestones": [
            {
                "key": "build",
                "title": "Build it",
                "desc": "As a user, I want the change.",
                "tasks": [
                    {
                        "key": "impl",
                        "title": "Implement it",
                        "desc": "Approach: do the work.",
                    }
                ],
            }
        ],
    }


@unittest.skipUnless(create_app is not None, "textual not installed")
class TestDraftPanel(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(os.path.join(self.tmp.name, "drafts.db"))

    async def test_draft_panel_shows_rows_and_selects(self) -> None:
        draft = drafts.create(self.store, document())
        app = create_app(str(self.store.path))
        async with app.run_test(size=(130, 40)) as pilot:
            await pilot.pause()
            panel = app.query_one("#plans-drafts")
            tree = app.query_one("#tree-drafts")
            self.assertTrue(panel.display)
            self.assertTrue(tree.display)
            self.assertEqual(len(tree.root.children), 1)
            label = str(tree.root.children[0].label)
            self.assertIn("D1", label)
            self.assertIn("Demo plan", label)
            self.assertIn("0/0", label)
            app.select_row("draft", draft.id)
            await pilot.pause()
            self.assertEqual(app.selected, ("draft", draft.id))
            head = str(app.query_one("#preview-head").render())
            self.assertIn("Demo plan", head)
            self.assertIn("review", head)

    async def test_revising_draft_shows_the_state_and_open_count(self) -> None:
        draft = drafts.create(self.store, document())
        drafts.annotate(self.store, draft.id, "plan:why", "change", "Sharpen")
        drafts.submit(self.store, draft.id)
        app = create_app(str(self.store.path))
        async with app.run_test(size=(130, 40)) as pilot:
            await pilot.pause()
            tree = app.query_one("#tree-drafts")
            label = str(tree.root.children[0].label)
            self.assertIn("1/1", label)
            self.assertIn("revising", label)

    async def test_promoted_draft_leaves_the_panel(self) -> None:
        draft = drafts.create(self.store, document())
        drafts.promote(self.store, draft.id)
        app = create_app(str(self.store.path))
        async with app.run_test(size=(130, 40)) as pilot:
            await pilot.pause()
            self.assertFalse(app.query_one("#plans-drafts").display)
            self.assertEqual(len(app.query_one("#tree-drafts").root.children), 0)

    async def test_plan_actions_are_refused_on_a_draft(self) -> None:
        draft = drafts.create(self.store, document())
        app = create_app(str(self.store.path))
        async with app.run_test(size=(130, 40)) as pilot:
            await pilot.pause()
            app.select_row("draft", draft.id)
            await pilot.pause()
            app.action_toggle_status()
            app.action_delete()
            app.action_add_criterion()
            await pilot.pause()
            self.assertEqual(self.store.get_draft(draft.id).status, "review")
            self.assertEqual(len(app.screen_stack), 1)

    async def test_draft_panel_stays_visible_in_the_narrow_layout(self) -> None:
        draft = drafts.create(self.store, document())
        app = create_app(str(self.store.path))
        async with app.run_test(size=(90, 40)) as pilot:
            await pilot.pause()
            self.assertTrue(app.query_one("#plans-drafts").display)
            self.assertFalse(app.query_one("#side").display)
            tree = app.query_one("#tree-drafts")
            self.assertEqual(len(tree.root.children), 1)
            app.select_row("draft", draft.id)
            await pilot.pause()
            self.assertEqual(app.selected, ("draft", draft.id))

    async def test_document_renders_one_body_per_block(self) -> None:
        draft = drafts.create(self.store, document())
        app = create_app(str(self.store.path))
        async with app.run_test(size=(130, 40)) as pilot:
            await pilot.pause()
            app.open_draft(draft.id)
            await pilot.pause()
            expected = drafts.detail(self.store, draft.id)
            bodies = list(app.screen.query(".draft-block-body"))
            self.assertEqual(len(bodies), len(expected.blocks))
            labels = [str(row.render()) for row in app.screen.query(".draft-block-label")]
            self.assertIn("Plan title [title]", labels)
            self.assertIn("Plan why [text]", labels)

    async def test_current_anchor_uses_the_focused_block(self) -> None:
        draft = drafts.create(self.store, document())
        app = create_app(str(self.store.path))
        async with app.run_test(size=(130, 40)) as pilot:
            await pilot.pause()
            app.open_draft(draft.id)
            await pilot.pause()
            bodies = list(app.screen.query(".draft-block-body"))
            bodies[1].focus()
            await pilot.pause()
            anchor = app.screen.current_anchor()
            self.assertIsNotNone(anchor)
            assert anchor is not None
            self.assertEqual(anchor.block_key, "plan:why")
            self.assertEqual(anchor.quote, "")

    async def test_current_anchor_uses_selected_text(self) -> None:
        draft = drafts.create(self.store, document())
        app = create_app(str(self.store.path))
        async with app.run_test(size=(130, 40)) as pilot:
            await pilot.pause()
            app.open_draft(draft.id)
            await pilot.pause()
            body = next(iter(app.screen.query(".draft-block-body")))
            body.focus()
            await pilot.pause()
            selection = Selection.from_offsets(Offset(0, 0), Offset(4, 0))
            app.screen.selections = {body: selection}
            anchor = app.screen.current_anchor()
            self.assertIsNotNone(anchor)
            assert anchor is not None
            self.assertEqual(anchor.block_key, "plan:title")
            self.assertEqual(anchor.quote, "Demo")
            self.assertEqual((anchor.start_offset, anchor.end_offset), (0, 4))

    async def test_current_anchor_spans_lines(self) -> None:
        draft = drafts.create(self.store, document(why="line one\nline two"))
        app = create_app(str(self.store.path))
        async with app.run_test(size=(130, 40)) as pilot:
            await pilot.pause()
            app.open_draft(draft.id)
            await pilot.pause()
            body = list(app.screen.query(".draft-block-body"))[1]
            body.focus()
            await pilot.pause()
            selection = Selection.from_offsets(Offset(5, 0), Offset(4, 1))
            app.screen.selections = {body: selection}
            anchor = app.screen.current_anchor()
            self.assertIsNotNone(anchor)
            assert anchor is not None
            self.assertEqual(anchor.quote, "one\nline")
            self.assertEqual((anchor.start_offset, anchor.end_offset), (5, 13))

    async def test_j_and_k_move_block_focus(self) -> None:
        draft = drafts.create(self.store, document())
        app = create_app(str(self.store.path))
        async with app.run_test(size=(130, 40)) as pilot:
            await pilot.pause()
            app.open_draft(draft.id)
            await pilot.pause()
            bodies = list(app.screen.query(".draft-block-body"))
            bodies[0].focus()
            await pilot.pause()
            app.screen.action_next_block()
            await pilot.pause()
            self.assertIs(app.screen.focused, bodies[1])
            app.screen.action_prev_block()
            await pilot.pause()
            self.assertIs(app.screen.focused, bodies[0])

    async def test_a_selection_across_blocks_is_refused(self) -> None:
        draft = drafts.create(self.store, document())
        app = create_app(str(self.store.path))
        async with app.run_test(size=(130, 40)) as pilot:
            await pilot.pause()
            app.open_draft(draft.id)
            await pilot.pause()
            bodies = list(app.screen.query(".draft-block-body"))
            selection = Selection.from_offsets(Offset(0, 0), Offset(1, 0))
            app.screen.selections = {bodies[0]: selection, bodies[1]: selection}
            self.assertIsNone(app.screen.current_anchor())

    async def test_annotation_form_saves_the_selected_quote(self) -> None:
        draft = drafts.create(self.store, document())
        app = create_app(str(self.store.path))
        async with app.run_test(size=(130, 40)) as pilot:
            await pilot.pause()
            app.open_draft(draft.id)
            await pilot.pause()
            body = list(app.screen.query(".draft-block-body"))[1]
            body.focus()
            await pilot.pause()
            selection = Selection.from_offsets(Offset(0, 0), Offset(3, 0))
            app.screen.selections = {body: selection}
            app.screen.action_annotate()
            await pilot.pause()
            self.assertEqual(type(app.screen).__name__, "AnnotationForm")
            form = app.screen
            form.query_one("#f-kind", Select).value = "change"
            form.query_one("#f-body", TextArea).text = "Sharpen this"
            await pilot.pause()
            form.query_one("#ok", Button).press()
            await pilot.pause()
            self.assertEqual(type(app.screen).__name__, "DraftScreen")
            annotations = drafts.list_annotations(self.store, draft.id)
            self.assertEqual(len(annotations), 1)
            self.assertEqual(annotations[0].kind, "change")
            self.assertEqual(annotations[0].body, "Sharpen this")
            self.assertEqual(annotations[0].quote, "Why")
            self.assertEqual((annotations[0].start_offset, annotations[0].end_offset), (0, 3))

    async def test_annotation_form_requires_text(self) -> None:
        draft = drafts.create(self.store, document())
        app = create_app(str(self.store.path))
        async with app.run_test(size=(130, 40)) as pilot:
            await pilot.pause()
            app.open_draft(draft.id)
            await pilot.pause()
            app.screen.action_annotate()
            await pilot.pause()
            form = app.screen
            form.query_one("#ok", Button).press()
            await pilot.pause()
            self.assertEqual(type(app.screen).__name__, "AnnotationForm")

    async def test_sidebar_lists_annotations_and_their_details(self) -> None:
        draft = drafts.create(self.store, document())
        drafts.annotate(self.store, draft.id, "plan:why", "question", "Why does this matter?")
        app = create_app(str(self.store.path))
        async with app.run_test(size=(130, 40)) as pilot:
            await pilot.pause()
            app.open_draft(draft.id)
            await pilot.pause()
            options = app.screen.query_one("#draft-annotations", OptionList)
            self.assertEqual(options.option_count, 1)
            detail = str(app.screen.query_one("#draft-annotation-detail").render())
            self.assertIn("question", detail)
            self.assertIn("Why does this matter?", detail)
            self.assertIn("plan:why", detail)

    async def test_enter_views_one_annotation(self) -> None:
        draft = drafts.create(self.store, document())
        drafts.annotate(self.store, draft.id, "plan:why", "question", "Why does this matter?")
        app = create_app(str(self.store.path))
        async with app.run_test(size=(130, 40)) as pilot:
            await pilot.pause()
            app.open_draft(draft.id)
            await pilot.pause()
            app.screen.query_one("#draft-annotations", OptionList).focus()
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            self.assertEqual(type(app.screen).__name__, "TextScreen")
            self.assertIn("Why does this matter?", app.screen.HELP)

    async def test_delete_open_annotation(self) -> None:
        draft = drafts.create(self.store, document())
        annotation = drafts.annotate(self.store, draft.id, "plan:why", "comment", "Remove me")
        app = create_app(str(self.store.path))
        async with app.run_test(size=(130, 40)) as pilot:
            await pilot.pause()
            app.open_draft(draft.id)
            await pilot.pause()
            app.screen.query_one("#draft-annotations", OptionList).focus()
            await pilot.pause()
            app.screen.action_delete_annotation()
            await pilot.pause()
            self.assertEqual(type(app.screen).__name__, "ConfirmScreen")
            app.screen.query_one("#ok", Button).press()
            await pilot.pause()
            self.assertIsNone(self.store.get_draft_annotation(annotation.id))

    async def test_dismiss_annotation_with_a_reason(self) -> None:
        draft = drafts.create(self.store, document())
        annotation = drafts.annotate(self.store, draft.id, "plan:why", "comment", "Maybe")
        app = create_app(str(self.store.path))
        async with app.run_test(size=(130, 40)) as pilot:
            await pilot.pause()
            app.open_draft(draft.id)
            await pilot.pause()
            app.screen.query_one("#draft-annotations", OptionList).focus()
            await pilot.pause()
            app.screen.action_dismiss_annotation()
            await pilot.pause()
            self.assertEqual(type(app.screen).__name__, "FilterPromptScreen")
            app.screen.query_one("#filter-input", Input).value = "not needed"
            app.screen.query_one("#ok", Button).press()
            await pilot.pause()
            row = self.store.get_draft_annotation(annotation.id)
            self.assertIsNotNone(row)
            assert row is not None
            self.assertEqual(row.status, "dismissed")
            self.assertEqual(row.response, "not needed")

    async def test_submit_feedback_moves_the_draft_to_revising(self) -> None:
        draft = drafts.create(self.store, document())
        drafts.annotate(self.store, draft.id, "plan:why", "change", "Sharpen")
        app = create_app(str(self.store.path))
        async with app.run_test(size=(130, 40)) as pilot:
            await pilot.pause()
            app.open_draft(draft.id)
            await pilot.pause()
            app.screen.action_submit_feedback()
            await pilot.pause()
            self.assertEqual(type(app.screen).__name__, "ConfirmScreen")
            app.screen.query_one("#ok", Button).press()
            await pilot.pause()
            updated = self.store.get_draft(draft.id)
            assert updated is not None
            self.assertEqual(updated.status, "revising")
            head = str(app.screen.query_one("#draft-head").render())
            self.assertIn("revising", head)

    async def test_promote_clean_draft_returns_to_the_plan_queue(self) -> None:
        draft = drafts.create(self.store, document())
        app = create_app(str(self.store.path))
        async with app.run_test(size=(130, 40)) as pilot:
            await pilot.pause()
            app.open_draft(draft.id)
            await pilot.pause()
            app.screen.action_promote()
            await pilot.pause()
            self.assertEqual(type(app.screen).__name__, "ConfirmScreen")
            app.screen.query_one("#ok", Button).press()
            await pilot.pause()
            self.assertEqual(len(app.screen_stack), 1)
            promotion = self.store.get_draft(draft.id)
            assert promotion is not None
            self.assertEqual(promotion.status, "promoted")
            self.assertIsNotNone(promotion.plan_id)
            self.assertEqual(app.selected, ("plan", promotion.plan_id))

    async def test_promote_refuses_open_annotations(self) -> None:
        draft = drafts.create(self.store, document())
        drafts.annotate(self.store, draft.id, "plan:why", "change", "Sharpen")
        app = create_app(str(self.store.path))
        async with app.run_test(size=(130, 40)) as pilot:
            await pilot.pause()
            app.open_draft(draft.id)
            await pilot.pause()
            app.screen.action_promote()
            await pilot.pause()
            self.assertEqual(type(app.screen).__name__, "DraftScreen")
            self.assertEqual(self.store.counts()["plans"], 0)

    async def test_draft_history_round_trips(self) -> None:
        draft = drafts.create(self.store, document())
        app = create_app(str(self.store.path))
        async with app.run_test(size=(130, 40)) as pilot:
            await pilot.pause()
            app.open_draft(draft.id)
            await pilot.pause()
            self.assertEqual(len(app.screen_stack), 2)
            app.action_history_back()
            await pilot.pause()
            self.assertEqual(len(app.screen_stack), 1)
            self.assertEqual(app.selected, ("draft", draft.id))
            app.action_history_forward()
            await pilot.pause()
            self.assertEqual(len(app.screen_stack), 2)
            self.assertEqual(type(app.screen).__name__, "DraftScreen")

    async def test_palette_offers_submit_and_promote_on_the_draft_screen(self) -> None:
        context = registry.Context(screen="draft", selected_kind="draft")
        availability = registry.palette_context(context)
        self.assertIsNone(availability["submit-draft"])
        self.assertIsNone(availability["promote-draft"])
        self.assertIsNotNone(availability["open-draft"])

    async def test_sidebar_shows_a_moved_anchor_after_revision(self) -> None:
        draft = drafts.create(self.store, document())
        drafts.annotate(self.store, draft.id, "plan:why", "change", "Sharpen", quote="Why")
        drafts.submit(self.store, draft.id)
        drafts.revise(
            self.store,
            draft.id,
            document(why="A sharper Why."),
            base_revision=1,
            actor="agent",
        )
        app = create_app(str(self.store.path))
        async with app.run_test(size=(130, 40)) as pilot:
            await pilot.pause()
            app.open_draft(draft.id)
            await pilot.pause()
            detail = str(app.screen.query_one("#draft-annotation-detail").render())
            self.assertIn("anchor moved", detail)
            head = str(app.screen.query_one("#draft-head").render())
            self.assertIn("review", head)
            self.assertIn("r2", head)

    async def test_sidebar_shows_an_agent_response(self) -> None:
        draft = drafts.create(self.store, document())
        annotation = drafts.annotate(self.store, draft.id, "plan:why", "question", "Why?")
        drafts.respond(self.store, annotation.id, "Because", actor="agent")
        app = create_app(str(self.store.path))
        async with app.run_test(size=(130, 40)) as pilot:
            await pilot.pause()
            app.open_draft(draft.id)
            await pilot.pause()
            detail = str(app.screen.query_one("#draft-annotation-detail").render())
            self.assertIn("addressed", detail)
            self.assertIn("response: Because", detail)

    async def test_block_level_annotation_from_focus(self) -> None:
        draft = drafts.create(self.store, document())
        app = create_app(str(self.store.path))
        async with app.run_test(size=(130, 40)) as pilot:
            await pilot.pause()
            app.open_draft(draft.id)
            await pilot.pause()
            app.screen.action_annotate()
            await pilot.pause()
            form = app.screen
            form.query_one("#f-body", TextArea).text = "Whole block note"
            form.query_one("#ok", Button).press()
            await pilot.pause()
            annotations = drafts.list_annotations(self.store, draft.id)
            self.assertEqual(len(annotations), 1)
            self.assertEqual(annotations[0].quote, "")
            self.assertEqual((annotations[0].start_offset, annotations[0].end_offset), (0, 0))

    async def test_empty_journal_keeps_the_drafts_panel_hidden(self) -> None:
        app = create_app(str(self.store.path))
        async with app.run_test(size=(130, 40)) as pilot:
            await pilot.pause()
            self.assertFalse(app.query_one("#plans-drafts").display)

    async def test_e_opens_the_draft_screen(self) -> None:
        draft = drafts.create(self.store, document())
        app = create_app(str(self.store.path))
        async with app.run_test(size=(130, 40)) as pilot:
            await pilot.pause()
            app.select_row("draft", draft.id)
            await pilot.pause()
            app.action_edit_selection()
            await pilot.pause()
            self.assertEqual(len(app.screen_stack), 2)
            self.assertEqual(type(app.screen).__name__, "DraftScreen")
            head = str(app.screen.query_one("#draft-head").render())
            self.assertIn("Demo plan", head)
            self.assertIn("0/0 open", head)
            bodies = list(app.screen.query(".draft-block-body"))
            self.assertTrue(bodies)
            self.assertIn("Demo plan", str(bodies[0].render()))
            await pilot.press("escape")
            await pilot.pause()
            self.assertEqual(len(app.screen_stack), 1)

    async def test_enter_opens_the_draft_screen(self) -> None:
        draft = drafts.create(self.store, document())
        app = create_app(str(self.store.path))
        async with app.run_test(size=(130, 40)) as pilot:
            await pilot.pause()
            app.select_row("draft", draft.id)
            tree = app.query_one("#tree-drafts")
            tree.focus()
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            self.assertEqual(len(app.screen_stack), 2)
            self.assertEqual(type(app.screen).__name__, "DraftScreen")

    async def test_palette_offers_open_draft_only_for_drafts(self) -> None:
        draft_context = registry.Context(screen="tree", selected_kind="draft")
        self.assertIsNone(registry.palette_context(draft_context)["open-draft"])
        plan_context = registry.Context(screen="tree", selected_kind="plan", has_plan=True)
        self.assertIsNotNone(registry.palette_context(plan_context)["open-draft"])


if __name__ == "__main__":
    unittest.main()
