"""Approval and diff actions from the palette."""

from __future__ import annotations

import os
import tempfile
import unittest

from lazyplan.core.entities import Status
from lazyplan.services import revisions
from lazyplan.store import Store

try:
    from lazyplan.presentation import tui as tui_mod
    from lazyplan.presentation.tui.screens import FilterPromptScreen, TextScreen
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
class ApprovalActionsTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "approval.db")
        store = Store(self.db)
        self.plan = store.add_plan("Approval plan", "What", goal="Why")
        self.milestone = store.add_milestone(self.plan.id, "M", "As a user.", actor="t")
        self.task = store.add_task(self.milestone.id, "T", "Commit: one.", actor="t")
        self.store = store
        self.app = tui_mod.create_app(self.db)
        self.app.override_mode = True

    async def asyncTearDown(self) -> None:
        self.tmp.cleanup()

    async def _approve(self, pilot, reason: str) -> None:
        self.app.selected = ("plan", self.plan.id)
        await _palette(pilot, "approve")
        self.assertIsInstance(self.app.screen, FilterPromptScreen)
        for char in reason:
            await pilot.press(char)
        await pilot.press("enter")
        await pilot.pause()

    async def test_approve_records_a_revision_and_audit_event(self) -> None:
        async with self.app.run_test(size=(120, 40)) as pilot:
            await settle(pilot)
            await self._approve(pilot, "reviewed")
            revision = Store(self.db).latest_revision(self.plan.id)
            self.assertIsNotNone(revision)
            assert revision is not None
            self.assertEqual(revision.reason, "reviewed")
            events = [event for event in Store(self.db).feed() if event["kind"] == "override"]
            self.assertTrue(
                any(
                    event["action"] == "approve" and "reviewed" in event["detail"]
                    for event in events
                )
            )

    async def test_diff_opens_a_read_only_overlay(self) -> None:
        async with self.app.run_test(size=(120, 40)) as pilot:
            await settle(pilot)
            await self._approve(pilot, "reviewed")
            Store(self.db).update_task(self.task.id, title="Renamed", reason="scope change")
            self.app.selected = ("plan", self.plan.id)
            await _palette(pilot, "diff")
            self.assertIsInstance(self.app.screen, TextScreen)
            text = str(self.app.screen.HELP)
            self.assertIn("diff from r1", text)
            self.assertIn("scope change", text)

    async def test_reapproval_after_drift_needs_a_reason(self) -> None:
        async with self.app.run_test(size=(120, 40)) as pilot:
            await settle(pilot)
            await self._approve(pilot, "reviewed")
            Store(self.db).update_task(self.task.id, title="Renamed", reason="scope change")
            self.app.selected = ("plan", self.plan.id)
            await _palette(pilot, "approve")
            await pilot.press("enter")
            await pilot.pause()
            revisions = Store(self.db).list_revisions(self.plan.id)
            self.assertEqual(len(revisions), 1)

    async def test_drift_done_override_asks_for_a_reason(self) -> None:
        store = Store(self.db)
        revisions.approve(store, self.plan.id, actor="t", enforced=True)
        store.update_task(self.task.id, title="Renamed", reason="scope change")
        store.set_status_raw("task", self.task.id, Status.DOING)
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
            self.assertIsInstance(self.app.screen, FilterPromptScreen)
            for char in "reviewed drift":
                await pilot.press(char)
            await pilot.press("enter")
            await pilot.pause()
            self.assertEqual(Store(self.db).get_task(self.task.id).status, Status.DONE)
            events = [event for event in Store(self.db).feed() if event["kind"] == "override"]
            self.assertTrue(
                any(
                    event["action"] == "status" and "reviewed drift" in event["detail"]
                    for event in events
                )
            )


if __name__ == "__main__":
    unittest.main()
