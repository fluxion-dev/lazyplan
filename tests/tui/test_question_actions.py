"""Plan question actions and the readiness effect."""

from __future__ import annotations

import os
import tempfile
import unittest

from lazyplan import services
from lazyplan.store import Store

try:
    from lazyplan.presentation import tui as tui_mod
    from lazyplan.presentation.tui.screens import FilterPromptScreen
except ImportError:  # pragma: no cover - stdlib-only interpreter
    tui_mod = None  # type: ignore[assignment]

from tests.support.pilot import settle


async def _palette(pilot, query: str) -> None:
    await pilot.press("c")
    await pilot.pause()
    for char in query:
        await pilot.press(char)
    await pilot.pause()
    await pilot.press("enter")
    await pilot.pause()
    await pilot.pause()


@unittest.skipUnless(tui_mod is not None and tui_mod._TEXTUAL_OK, "textual not installed")
class QuestionActionsTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "questions.db")
        store = Store(self.db)
        self.plan = store.add_plan("Question plan", "What", goal="Why")
        store.add_milestone(self.plan.id, "M", "As a user.", actor="t")
        self.store = store
        self.app = tui_mod.create_app(self.db)
        self.app.override_mode = True

    async def asyncTearDown(self) -> None:
        self.tmp.cleanup()

    async def test_add_resolve_and_reopen_a_question(self) -> None:
        async with self.app.run_test(size=(120, 40)) as pilot:
            await settle(pilot)
            self.app.selected = ("plan", self.plan.id)
            await _palette(pilot, "add question")
            self.assertIsInstance(self.app.screen, FilterPromptScreen)
            for char in "which host":
                await pilot.press(char)
            await pilot.press("enter")
            await pilot.pause()
            questions = Store(self.db).list_questions(self.plan.id, status="all")
            self.assertEqual(len(questions), 1)
            question_id = questions[0].id

            await _palette(pilot, "resolve question")
            for char in str(question_id):
                await pilot.press(char)
            await pilot.press("enter")
            await pilot.pause()
            self.assertEqual(
                Store(self.db).list_questions(self.plan.id, status="resolved")[0].id,
                question_id,
            )

            await _palette(pilot, "reopen question")
            for char in str(question_id):
                await pilot.press(char)
            await pilot.press("enter")
            await pilot.pause()
            self.assertEqual(
                Store(self.db).list_questions(self.plan.id, status="open")[0].id,
                question_id,
            )

    async def test_open_question_blocks_readiness(self) -> None:
        services.add_question(self.store, self.plan.id, "which host", actor="t")
        result = services.plan_ready(self.store, self.plan.id)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertFalse(result.ready)
        self.assertIn("questions", {check.id for check in result.checks if not check.ok})


if __name__ == "__main__":
    unittest.main()
