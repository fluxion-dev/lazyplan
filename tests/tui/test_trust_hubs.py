"""Trust hubs: selectable lists, previews, and every trust action."""

from __future__ import annotations

import os
import tempfile
import unittest
from unittest import mock

from lazyplan.store import Store
from tests.support.pilot import settle

try:
    from textual.widgets import Input, OptionList

    from lazyplan.presentation import tui as tui_mod
    from lazyplan.presentation.tui.screens.forms import (
        ConfirmScreen,
        FilterPromptScreen,
        ProveScreen,
    )
    from lazyplan.presentation.tui.screens.hub import (
        CriteriaHub,
        EvidenceHub,
        QuestionsHub,
        ReferencesHub,
    )
except ImportError:  # pragma: no cover - stdlib-only interpreter
    tui_mod = None  # type: ignore[assignment]


@unittest.skipUnless(tui_mod is not None and tui_mod._TEXTUAL_OK, "textual not installed")
class TrustHubTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "hub.db")
        store = Store(self.db)
        self.plan = store.add_plan("Hub", "What", goal="Why")
        self.milestone = store.add_milestone(self.plan.id, "M", "As a user.")
        self.task = store.add_task(self.milestone.id, "T", "Commit: one.")
        self.criteria = [
            store.add_criteria("task", self.task.id, "First criterion"),
            store.add_criteria("task", self.task.id, "Second criterion"),
        ]
        self.store = Store(self.db)

    async def asyncTearDown(self) -> None:
        self.tmp.cleanup()

    def _app(self):
        self.app = tui_mod.create_app(self.db)
        self.app.override_mode = True
        return self.app

    async def test_criteria_hub_lists_and_previews(self) -> None:
        app = self._app()
        async with app.run_test(size=(120, 40)) as pilot:
            await settle(pilot)
            app.push_screen(CriteriaHub(self.store, "task", self.task.id))
            await pilot.pause()
            options = app.screen.query_one("#hub-list", OptionList)
            self.assertEqual(options.option_count, 2)
            preview = str(app.screen.query_one("#hub-preview-body").render())
            self.assertIn("First criterion", preview)
            self.assertIn("evidence", preview)
            await pilot.press("down")
            await pilot.pause()
            self.assertEqual(options.highlighted, 1)

    async def test_criteria_add_toggle_and_delete(self) -> None:
        app = self._app()
        async with app.run_test(size=(120, 40)) as pilot:
            await settle(pilot)
            app.push_screen(CriteriaHub(self.store, "task", self.task.id))
            await pilot.pause()
            await pilot.press("a")
            await pilot.pause()
            self.assertIsInstance(app.screen, FilterPromptScreen)
            app.screen.query_one("#filter-input", Input).value = "Third criterion"
            await pilot.press("enter")
            await pilot.pause()
            self.assertEqual(len(Store(self.db).list_criteria("task", self.task.id)), 3)

            await pilot.press("x")
            await pilot.pause()
            self.assertTrue(any(c.done for c in Store(self.db).list_criteria("task", self.task.id)))

            await pilot.press("d")
            await pilot.pause()
            self.assertIsInstance(app.screen, ConfirmScreen)
            app.screen.dismiss(True)
            await pilot.pause()
            self.assertEqual(len(Store(self.db).list_criteria("task", self.task.id)), 2)

    async def test_criteria_relates_and_unrelates_a_task(self) -> None:
        app = self._app()
        async with app.run_test(size=(120, 40)) as pilot:
            await settle(pilot)
            app.push_screen(CriteriaHub(self.store, "task", self.task.id))
            await pilot.pause()
            await pilot.press("l")
            await pilot.pause()
            self.assertIsInstance(app.screen, FilterPromptScreen)
            app.screen.query_one("#filter-input", Input).value = str(self.task.id)
            await pilot.press("enter")
            await pilot.pause()
            self.assertEqual(
                [task.id for task in Store(self.db).criterion_tasks(self.criteria[0].id)],
                [self.task.id],
            )
            await pilot.press("L")
            await pilot.pause()
            app.screen.query_one("#filter-input", Input).value = str(self.task.id)
            await pilot.press("enter")
            await pilot.pause()
            self.assertEqual(Store(self.db).criterion_tasks(self.criteria[0].id), [])

    async def test_criteria_opens_evidence_and_prove_targets_the_selection(self) -> None:
        app = self._app()
        async with app.run_test(size=(120, 40)) as pilot:
            await settle(pilot)
            app.push_screen(CriteriaHub(self.store, "task", self.task.id))
            await pilot.pause()
            await pilot.press("down")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            self.assertIsInstance(app.screen, EvidenceHub)
            await pilot.press("p")
            await pilot.pause()
            self.assertIsInstance(app.screen, ProveScreen)
            self.assertEqual(
                app.screen.query_one("#p-criterion", Input).value, str(self.criteria[1].id)
            )

    async def test_evidence_hub_shows_state_and_opens_commit(self) -> None:
        self.store.add_evidence(
            self.criteria[0].id, command="pytest", exit_code=0, commit_sha="a" * 40
        )
        app = self._app()
        async with app.run_test(size=(120, 40)) as pilot:
            await settle(pilot)
            app.push_screen(EvidenceHub(self.store, self.criteria[0].id))
            await pilot.pause()
            options = app.screen.query_one("#hub-list", OptionList)
            self.assertEqual(options.option_count, 1)
            preview = str(app.screen.query_one("#hub-preview-body").render())
            self.assertIn("pass", preview)
            self.assertIn("pytest", preview)
            with mock.patch.object(app, "copy_to_clipboard") as copy:
                await pilot.press("o")
                await pilot.pause()
            copy.assert_called_once_with("a" * 40)

    async def test_questions_hub_resolves_and_reopens(self) -> None:
        question = self.store.add_question(self.plan.id, "Which host?")
        app = self._app()
        async with app.run_test(size=(120, 40)) as pilot:
            await settle(pilot)
            app.push_screen(QuestionsHub(self.store, self.plan.id))
            await pilot.pause()
            preview = str(app.screen.query_one("#hub-preview-body").render())
            self.assertIn("block plan ready", preview)
            await pilot.press("x")
            await pilot.pause()
            self.assertEqual(Store(self.db).get_question(question.id).status, "resolved")
            await pilot.press("x")
            await pilot.pause()
            self.assertEqual(Store(self.db).get_question(question.id).status, "open")

    async def test_references_hub_links_opens_and_unlinks(self) -> None:
        app = self._app()
        async with app.run_test(size=(120, 40)) as pilot:
            await settle(pilot)
            app.push_screen(ReferencesHub(self.store, self.plan.id))
            await pilot.pause()
            await pilot.press("a")
            await pilot.pause()
            app.screen.query_one("#filter-input", Input).value = "https://example.com/issue/1"
            await pilot.press("enter")
            await pilot.pause()
            refs = Store(self.db).list_refs(self.plan.id)
            self.assertEqual(len(refs), 1)
            with mock.patch("webbrowser.open") as opener:
                await pilot.press("o")
                await pilot.pause()
            opener.assert_called_once_with("https://example.com/issue/1")
            await pilot.press("d")
            await pilot.pause()
            app.screen.dismiss(True)
            await pilot.pause()
            self.assertEqual(Store(self.db).list_refs(self.plan.id), [])

    async def test_palette_opens_each_trust_hub(self) -> None:
        app = self._app()
        async with app.run_test(size=(120, 40)) as pilot:
            await settle(pilot)
            app.selected = ("task", self.task.id)
            for query, expected in (
                ("criteria hub", CriteriaHub),
                ("questions hub", QuestionsHub),
                ("references hub", ReferencesHub),
            ):
                with self.subTest(query=query):
                    await pilot.press("c")
                    await pilot.pause()
                    app.screen.query_one("#palette-input", Input).value = query
                    await pilot.press("enter")
                    await pilot.pause()
                    self.assertIsInstance(app.screen, expected)
                    await pilot.press("escape")
                    await pilot.pause()

    async def test_hub_actions_come_from_the_registry(self) -> None:
        from lazyplan.presentation.shared import registry

        for kind in ("criteria", "evidence", "questions", "references"):
            with self.subTest(kind=kind):
                pairs = registry.hub_actions(kind)
                self.assertGreater(len(pairs), 0)
                for action_id, label in pairs:
                    action = registry.by_id(action_id)
                    self.assertIsNotNone(action)
                    assert action is not None
                    self.assertEqual(action.label, label)

    async def test_empty_states_and_viewports(self) -> None:
        empty = Store(self.db).add_milestone(self.plan.id, "Empty", "No criteria here.")
        for size in ((80, 24), (120, 40)):
            with self.subTest(size=size):
                app = self._app()
                async with app.run_test(size=size) as pilot:
                    await settle(pilot)
                    app.push_screen(CriteriaHub(self.store, "milestone", empty.id))
                    await pilot.pause()
                    preview = str(app.screen.query_one("#hub-preview-body").render())
                    self.assertIn("No criteria yet", preview)
                    page = app.screen.query_one("#hub-page")
                    self.assertLessEqual(page.region.x + page.region.width, size[0])
                    self.assertLessEqual(page.region.y + page.region.height, size[1])
