"""Prove evidence from the screen and gate a task finish."""

from __future__ import annotations

import os
import tempfile
import unittest

from lazyplan.core.entities import Status
from lazyplan.store import Store

try:
    from textual.widgets import Input

    from lazyplan.presentation import tui as tui_mod
    from lazyplan.presentation.tui.screens import FilterPromptScreen, ProveScreen
except ImportError:  # pragma: no cover - stdlib-only interpreter
    tui_mod = None  # type: ignore[assignment]

from tests.support.pilot import settle


@unittest.skipUnless(tui_mod is not None and tui_mod._TEXTUAL_OK, "textual not installed")
class EvidenceActionsTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "evidence.db")
        store = Store(self.db)
        self.plan = store.add_plan("Evidence plan", "What", goal="Why")
        self.milestone = store.add_milestone(self.plan.id, "M", "As a user.", actor="t")
        self.task = store.add_task(self.milestone.id, "T", "Commit: one.", actor="t")
        self.criterion = store.add_criteria("task", self.task.id, "Works", actor="t")
        self.store = store
        self.app = tui_mod.create_app(self.db)
        self.app.override_mode = True

    async def asyncTearDown(self) -> None:
        self.tmp.cleanup()

    async def _prove(self, pilot, command: str, exit_code: str) -> None:
        self.app.selected = ("task", self.task.id)
        await pilot.press("p")
        await pilot.pause()
        self.assertIsInstance(self.app.screen, ProveScreen)
        self.app.screen.query_one("#p-command", Input).value = command
        self.app.screen.query_one("#p-exit", Input).value = exit_code
        await pilot.click("#ok")
        await pilot.pause()

    async def test_passing_evidence_ticks_the_criterion(self) -> None:
        async with self.app.run_test(size=(120, 40)) as pilot:
            await settle(pilot)
            await self._prove(pilot, "pytest", "0")
            criteria = Store(self.db).list_criteria("task", self.task.id)
            self.assertTrue(criteria[0].done)
            rows = Store(self.db).list_evidence(self.criterion.id)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].command, "pytest")
            events = [event for event in Store(self.db).feed() if event["kind"] == "override"]
            self.assertTrue(
                any(
                    event["action"] == "criterion prove" and "pytest" in event["detail"]
                    for event in events
                )
            )

    async def test_failing_evidence_leaves_the_criterion_open(self) -> None:
        async with self.app.run_test(size=(120, 40)) as pilot:
            await settle(pilot)
            await self._prove(pilot, "pytest", "1")
            criteria = Store(self.db).list_criteria("task", self.task.id)
            self.assertFalse(criteria[0].done)

    async def test_finish_without_passing_evidence_asks_for_a_reason(self) -> None:
        self.store.set_status_raw("task", self.task.id, Status.DOING)
        async with self.app.run_test(size=(120, 40)) as pilot:
            await settle(pilot)
            self.app.selected = ("task", self.task.id)
            await pilot.press("s")
            await pilot.pause()
            self.assertIsInstance(self.app.screen, FilterPromptScreen)
            await pilot.press("escape")
            await pilot.pause()
            self.assertEqual(Store(self.db).get_task(self.task.id).status, Status.DOING)

            await pilot.press("s")
            await pilot.pause()
            for char in "accepted by human":
                await pilot.press(char)
            await pilot.press("enter")
            await pilot.pause()
            self.assertEqual(Store(self.db).get_task(self.task.id).status, Status.DONE)
            events = [event for event in Store(self.db).feed() if event["kind"] == "override"]
            self.assertTrue(
                any(
                    event["action"] == "status" and "accepted by human" in event["detail"]
                    for event in events
                )
            )


if __name__ == "__main__":
    unittest.main()
