"""Finish task: gate warning, override reason, and audit event."""

from __future__ import annotations

import os
import tempfile
import unittest
from unittest import mock

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
class FinishActionsTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "finish.db")
        store = Store(self.db)
        plan = store.add_plan("Finish plan", "What", goal="Why")
        milestone = store.add_milestone(plan.id, "M", "As a user.", actor="t")
        self.task = store.add_task(milestone.id, "T", "Commit: one.", actor="t")
        self.store = store
        self.app = tui_mod.create_app(self.db)
        self.app.override_mode = True

    async def asyncTearDown(self) -> None:
        self.tmp.cleanup()

    async def test_gate_warning_requires_a_reason_and_retries(self) -> None:
        responses = [
            services.GateError("task #1 needs passing evidence"),
            {"task": self.task.id, "done": True},
        ]
        with mock.patch("lazyplan.services.finish_task", side_effect=responses) as finish:
            async with self.app.run_test(size=(120, 40)) as pilot:
                await settle(pilot)
                self.app.selected = ("task", self.task.id)
                await _palette(pilot, "finish task")
                self.assertIsInstance(self.app.screen, FilterPromptScreen)
                for char in "accepted by human":
                    await pilot.press(char)
                await pilot.press("enter")
                await pilot.pause()
                self.assertEqual(finish.call_count, 2)
                self.assertEqual(finish.call_args.kwargs["override"], "accepted by human")
                events = [event for event in Store(self.db).feed() if event["kind"] == "override"]
                self.assertTrue(
                    any(
                        event["action"] == "finish" and "accepted by human" in event["detail"]
                        for event in events
                    )
                )


if __name__ == "__main__":
    unittest.main()
