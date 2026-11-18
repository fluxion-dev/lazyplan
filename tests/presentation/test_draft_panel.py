"""The main-screen plan drafts panel: rows, selection, and guards."""

from __future__ import annotations

import os
import tempfile
import unittest

from lazyplan.presentation.shared import registry
from lazyplan.services import drafts
from lazyplan.store import Store

try:
    from lazyplan.presentation.tui import create_app
except ImportError:  # pragma: no cover - textual not installed
    create_app = None  # type: ignore[assignment]


def document() -> dict:
    return {
        "plan": {
            "key": "demo-plan",
            "title": "Demo plan",
            "why": "Why this matters.",
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
            body = str(app.screen.query_one("#draft-body").render())
            self.assertIn("Demo plan", body)
            self.assertIn("annotations:", body)
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
