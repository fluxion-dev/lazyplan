"""Dialog titles, criterion routing, and compact form CSS stay intentional."""

from __future__ import annotations

import os
import re
import tempfile
import unittest
from pathlib import Path

from lazyplan.store import Store

try:
    from textual.widgets import Button, Checkbox, Input, TextArea, Tree

    from lazyplan.presentation.tui import create_app
    from lazyplan.presentation.tui.screens.forms import (
        ConfirmScreen,
        CriterionScreen,
        FilterPromptScreen,
        NewMilestoneScreen,
        NewPlanScreen,
        NewTaskScreen,
        RefScreen,
    )
    from lazyplan.presentation.tui.screens.hub_kinds import CriteriaHub
except ImportError:  # pragma: no cover - stdlib-only interpreter
    FilterPromptScreen = None  # type: ignore[assignment]
    CriterionScreen = None  # type: ignore[assignment]
    CriteriaHub = None  # type: ignore[assignment]
    create_app = None  # type: ignore[assignment]
    ConfirmScreen = NewMilestoneScreen = NewPlanScreen = NewTaskScreen = None  # type: ignore[assignment]
    RefScreen = None  # type: ignore[assignment]
    Button = Checkbox = Input = TextArea = Tree = None  # type: ignore[assignment,misc]

CSS = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "lazyplan"
    / "presentation"
    / "tui"
    / "css"
    / "screens.tcss"
)
COLOUR_LITERAL = re.compile(r"#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(")


async def _open_screen(app, pilot, screen):
    """Push one modal, measure the dialog, and close it again."""
    app.push_screen(screen)
    await pilot.pause()
    dialog = app.screen.query_one("#dlg")
    measurements = {
        "width": dialog.size.width,
        "region": dialog.region,
        "entity": dialog.has_class("entity-form"),
        "tall": dialog.has_class("form-tall"),
        "areas": [(area.size.width, area.size.height) for area in app.screen.query(TextArea)],
        "buttons": {
            button.id: (button.display, button.region) for button in app.screen.query(Button)
        },
    }
    app.pop_screen()
    await pilot.pause()
    return measurements


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


@unittest.skipUnless(create_app is not None, "textual not installed")
class DialogSizingTest(unittest.IsolatedAsyncioTestCase):
    async def _app(self, size: tuple[int, int]):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        store = Store(os.path.join(self.tmp.name, "sizing.db"))
        plan = store.add_plan("Plan title", "What we build", goal="Why we build")
        milestone = store.add_milestone(plan.id, "Milestone title", "Details")
        return create_app(str(store.path)), store, plan, milestone

    async def test_entity_forms_use_the_screen_at_120x40(self) -> None:
        app, _store, plan, milestone = await self._app((120, 40))
        screens = [
            NewPlanScreen(),
            NewMilestoneScreen(plan.id, context=f"P{plan.id}"),
            NewTaskScreen(milestone.id, context=f"M{milestone.id}"),
        ]
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            for screen in screens:
                measured = await _open_screen(app, pilot, screen)
                self.assertTrue(measured["entity"])
                self.assertTrue(measured["tall"])
                self.assertGreaterEqual(measured["width"], 100)
                self.assertGreaterEqual(len(measured["areas"]), 1)
                for _width, height in measured["areas"]:
                    self.assertGreaterEqual(height, 8)

    async def test_criterion_and_reference_forms_share_the_width(self) -> None:
        app, _store, _plan, _milestone = await self._app((120, 40))
        screens = [CriterionScreen("Attention fits"), RefScreen()]
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            for screen in screens:
                measured = await _open_screen(app, pilot, screen)
                self.assertTrue(measured["entity"])
                self.assertFalse(measured["tall"])
                self.assertGreaterEqual(measured["width"], 100)
                self.assertEqual(measured["areas"], [])

    async def test_prompts_and_confirms_stay_compact(self) -> None:
        app, _store, _plan, _milestone = await self._app((120, 40))
        screens = [FilterPromptScreen(), ConfirmScreen("Delete task #3?")]
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            for screen in screens:
                measured = await _open_screen(app, pilot, screen)
                self.assertFalse(measured["entity"])
                self.assertFalse(measured["tall"])
                self.assertLessEqual(measured["width"], 84)

    async def test_plan_form_stays_inside_80x24(self) -> None:
        app, _store, _plan, _milestone = await self._app((80, 24))
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            measured = await _open_screen(app, pilot, NewPlanScreen())
            region = measured["region"]
            self.assertLessEqual(region.right, 80)
            self.assertLessEqual(region.bottom, 24)
            self.assertGreaterEqual(len(measured["areas"]), 1)
            for name in ("ok", "cancel"):
                display, button_region = measured["buttons"][name]
                self.assertTrue(display)
                self.assertGreaterEqual(button_region.y, region.y)
                self.assertLessEqual(button_region.bottom, region.bottom)


class DialogCssTest(unittest.TestCase):
    def test_entity_dialogs_scope_the_larger_scale(self) -> None:
        text = CSS.read_text(encoding="utf-8")
        self.assertIn("#dlg.entity-form {", text)
        self.assertIn("max-width: 120;", text)
        self.assertIn("#dlg.form-tall {", text)
        self.assertIn("height: 88%;", text)
        self.assertIn("#dlg.form-tall TextArea {", text)
        self.assertIn("min-height: 8;", text)
        self.assertIn("Screen.compact #dlg.entity-form {", text)
        self.assertIn("Screen.short #dlg.form-tall {", text)
        self.assertNotIn("#f-why", text)
        self.assertIsNone(COLOUR_LITERAL.search(text))

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
