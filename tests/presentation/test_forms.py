"""Dialog titles, criterion routing, and compact form CSS stay intentional."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from lazyplan.store import Store

try:
    from textual.widgets import Button, Checkbox, Input, Tree

    from lazyplan.presentation.tui import create_app
    from lazyplan.presentation.tui.screens.forms import CriterionScreen, FilterPromptScreen
    from lazyplan.presentation.tui.screens.hub_kinds import CriteriaHub
except ImportError:  # pragma: no cover - stdlib-only interpreter
    FilterPromptScreen = None  # type: ignore[assignment]
    CriterionScreen = None  # type: ignore[assignment]
    CriteriaHub = None  # type: ignore[assignment]
    create_app = None  # type: ignore[assignment]
    Button = Checkbox = Input = Tree = None  # type: ignore[assignment,misc]

CSS = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "lazyplan"
    / "presentation"
    / "tui"
    / "css"
    / "screens.tcss"
)


@unittest.skipUnless(FilterPromptScreen is not None, "textual not installed")
class PromptTitleTest(unittest.TestCase):
    def test_prompt_title_names_the_action(self) -> None:
        infer = FilterPromptScreen._infer_title
        self.assertEqual(infer("New criterion on task 1"), "CRITERION")
        self.assertEqual(infer("Approve P1? Why? (required after drift)"), "APPROVE")
        self.assertEqual(infer("Delete task #3? Why?"), "DELETE")
        self.assertEqual(infer("Start session"), "SESSION")
        self.assertEqual(infer("Link pull request"), "PULL REQUEST")
        self.assertEqual(infer("Filter tree by text (empty clears)"), "FILTER")


@unittest.skipUnless(create_app is not None, "textual not installed")
class CriterionFormTest(unittest.IsolatedAsyncioTestCase):
    async def _app_and_plan(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        store = Store(os.path.join(self.tmp.name, "forms.db"))
        plan = store.add_plan("Plan title", "What we build", goal="Why we build")
        return create_app(str(store.path)), store, plan

    async def test_the_tree_adds_a_criterion_through_the_form(self) -> None:
        app, store, plan = await self._app_and_plan()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            tree = app.query_one("#tree", Tree)
            tree.focus()
            tree.select_node(tree.root.children[0])
            await pilot.pause()
            app.action_add_criterion()
            await pilot.pause()
            self.assertIsInstance(app.screen, CriterionScreen)
            self.assertEqual(app.screen.query_one("#ok", Button).label, "Add")
            app.screen.query_one("#c-text", Input).value = "Attention fits"
            app.screen.query_one("#ok", Button).press()
            await pilot.pause()
            self.assertEqual(
                [criterion.text for criterion in store.list_criteria("plan", plan.id)],
                ["Attention fits"],
            )

    async def test_the_hub_edits_the_same_prefilled_form(self) -> None:
        app, store, plan = await self._app_and_plan()
        criterion = store.add_criteria("plan", plan.id, "Old text", actor="test")
        store.update_criterion(criterion.id, done=True, actor="test")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            hub = CriteriaHub(store, "plan", plan.id)
            app.push_screen(hub)
            await pilot.pause()
            hub.edit_row()
            await pilot.pause()
            self.assertIsInstance(app.screen, CriterionScreen)
            self.assertEqual(app.screen.query_one("#ok", Button).label, "Save")
            self.assertEqual(app.screen.query_one("#c-text", Input).value, "Old text")
            self.assertTrue(app.screen.query_one("#c-done", Checkbox).value)
            app.screen.query_one("#c-text", Input).value = "New text"
            app.screen.query_one("#ok", Button).press()
            await pilot.pause()
            updated = store.get_criterion(criterion.id)
            assert updated is not None
            self.assertEqual(updated.text, "New text")
            self.assertTrue(updated.done)


class DialogCssTest(unittest.TestCase):
    def test_dialog_fields_and_buttons_share_one_compact_scale(self) -> None:
        text = CSS.read_text(encoding="utf-8")
        self.assertIn("#dlg Input,\n#dlg Select {", text)
        self.assertIn("height: 3;", text)
        self.assertIn("#dlg TextArea {", text)
        self.assertIn("height: 5;", text)
        self.assertIn("#dlg Button, #help Button {", text)
        self.assertIn("height: 1;", text)


if __name__ == "__main__":
    unittest.main()
