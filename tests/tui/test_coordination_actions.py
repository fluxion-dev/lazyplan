"""Claim, block, and unblock overrides from the palette."""

from __future__ import annotations

import os
import tempfile
import unittest

from lazyplan.core.entities import Status
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
class CoordinationActionsTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "claims.db")
        store = Store(self.db)
        self.plan = store.add_plan("Claim plan", "What", goal="Why")
        self.milestone = store.add_milestone(self.plan.id, "M", "As a user.", actor="t")
        self.task = store.add_task(self.milestone.id, "T", "Commit: one.", actor="t")
        self.store = store
        self.app = tui_mod.create_app(self.db)
        self.app.override_mode = True

    async def asyncTearDown(self) -> None:
        self.tmp.cleanup()

    async def _reason(self, pilot, text: str) -> None:
        self.assertIsInstance(self.app.screen, FilterPromptScreen)
        for char in text:
            await pilot.press(char)
        await pilot.press("enter")
        await pilot.pause()

    async def test_claim_block_and_unblock(self) -> None:
        async with self.app.run_test(size=(120, 40)) as pilot:
            await settle(pilot)
            self.app.selected = ("task", self.task.id)
            await _palette(pilot, "claim task")
            self.assertIsNotNone(Store(self.db).get_claim(self.task.id))
            self.assertEqual(Store(self.db).get_task(self.task.id).status.value, "doing")

            await _palette(pilot, "block task")
            await self._reason(pilot, "waiting on design")
            task = Store(self.db).get_task(self.task.id)
            self.assertTrue(task.blocked)
            self.assertIn("waiting on design", task.blocked_reason)

            await _palette(pilot, "unblock task")
            self.assertFalse(Store(self.db).get_task(self.task.id).blocked)
            events = [event for event in Store(self.db).feed() if event["kind"] == "override"]
            actions = {event["action"] for event in events}
            self.assertTrue({"claim", "block", "unblock"} <= actions)

    async def test_status_move_releases_the_lease(self) -> None:
        self.store.claim_task(self.task.id, "alice", 300)
        self.store.set_status_raw("task", self.task.id, Status.DOING)
        async with self.app.run_test(size=(120, 40)) as pilot:
            await settle(pilot)
            self.app.selected = ("task", self.task.id)
            await pilot.press("s")
            await pilot.pause()
            self.assertEqual(Store(self.db).get_task(self.task.id).status.value, "done")
            self.assertIsNone(Store(self.db).get_claim(self.task.id))

    async def test_move_to_todo_releases_the_lease(self) -> None:
        self.store.claim_task(self.task.id, "alice", 300)
        self.store.set_status_raw("task", self.task.id, Status.DOING)
        async with self.app.run_test(size=(120, 40)) as pilot:
            await settle(pilot)
            self.app.selected = ("task", self.task.id)
            self.app.action_move(Status.TODO)
            await pilot.pause()
            self.assertEqual(Store(self.db).get_task(self.task.id).status.value, "todo")
            self.assertIsNone(Store(self.db).get_claim(self.task.id))

    async def test_overlapping_claim_asks_for_a_reason(self) -> None:
        other = self.store.add_task(self.milestone.id, "Other", "Commit: one.", actor="t")
        self.store.add_touchpoint(self.task.id, "src/app", actor="t")
        self.store.add_touchpoint(other.id, "src/app/api.py", actor="t")
        self.store.claim_task(other.id, "alice", 300)
        async with self.app.run_test(size=(120, 40)) as pilot:
            await settle(pilot)
            self.app.selected = ("task", self.task.id)
            await _palette(pilot, "claim task")
            await self._reason(pilot, "take the overlap")
            claim = Store(self.db).get_claim(self.task.id)
            self.assertIsNotNone(claim)
            assert claim is not None
            self.assertEqual(claim.actor, "tui")
            events = [event for event in Store(self.db).feed() if event["kind"] == "override"]
            self.assertTrue(
                any(
                    event["action"] == "claim" and "take the overlap" in event["detail"]
                    for event in events
                )
            )


if __name__ == "__main__":
    unittest.main()
