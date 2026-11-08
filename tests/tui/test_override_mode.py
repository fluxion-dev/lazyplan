"""Manual override mode: read-only by default, audited writes when armed."""

from __future__ import annotations

import os
import tempfile
import unittest

from lazyplan.core.entities import Status
from lazyplan.presentation.shared.palette import by_id
from lazyplan.store import Store

try:
    from textual.widgets import Static

    from lazyplan.presentation import tui as tui_mod
except ImportError:  # pragma: no cover - stdlib-only interpreter
    tui_mod = None  # type: ignore[assignment]

from tests.support.pilot import settle


async def _palette(pilot, query: str) -> None:
    """Drive the modal palette: open with c, type query, run first match."""
    await pilot.press("c")
    await pilot.pause()
    for char in query:
        await pilot.press(char)
    await pilot.pause()
    await pilot.press("enter")
    await pilot.pause()
    await pilot.pause()


@unittest.skipUnless(tui_mod is not None and tui_mod._TEXTUAL_OK, "textual not installed")
class OverrideModeTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "override.db")
        store = Store(self.db)
        plan = store.add_plan("P", actor="fixture")
        milestone = store.add_milestone(plan.id, "M", "As a user.", actor="fixture")
        self.task = store.add_task(
            milestone.id, "T", "Commit: one.\n\nVerify: test.", actor="fixture"
        )
        self.store = store
        self.app = tui_mod.create_app(self.db)

    async def asyncTearDown(self) -> None:
        self.tmp.cleanup()

    def _status(self) -> str:
        task = Store(self.db).get_task(self.task.id)
        assert task is not None
        return task.status.value

    async def test_writes_are_blocked_until_override_mode(self) -> None:
        async with self.app.run_test(size=(120, 40)) as pilot:
            await settle(pilot)
            self.app.selected = ("task", self.task.id)
            await pilot.press("s")
            await pilot.pause()
            self.assertEqual(self._status(), Status.TODO.value)
            self.assertEqual(
                [event for event in Store(self.db).feed() if event["kind"] == "override"],
                [],
            )

            await pilot.press("O")
            await pilot.pause()
            self.assertTrue(self.app.override_mode)
            self.assertTrue(self.app.query_one("#mode", Static).display)
            self.assertIn("MANUAL OVERRIDE", str(self.app.query_one("#mode", Static).render()))
            self.assertIn("OVERRIDE", str(self.app.query_one("#nav").border_subtitle))

            await pilot.press("s")
            await pilot.pause()
            self.assertEqual(self._status(), Status.DOING.value)
            events = [event for event in Store(self.db).feed() if event["kind"] == "override"]
            self.assertTrue(
                any(event["action"] == "status" and event["actor"] == "tui" for event in events)
            )

            await pilot.press("O")
            await pilot.pause()
            self.assertFalse(self.app.override_mode)
            self.assertFalse(self.app.query_one("#mode", Static).display)
            self.assertEqual(str(self.app.query_one("#nav").border_subtitle), "")
            await pilot.press("s")
            await pilot.pause()
            self.assertEqual(self._status(), Status.DOING.value)

    async def test_palette_has_the_override_command(self) -> None:
        command = by_id("toggle-override")
        assert command is not None
        self.assertEqual(command.key, "O")
        self.assertIn("override", command.aliases)

    async def test_detail_edit_requires_override(self) -> None:
        async with self.app.run_test(size=(120, 40)) as pilot:
            await settle(pilot)
            self.app.selected = ("task", self.task.id)
            await pilot.press("enter")
            await pilot.pause()
            screen = self.app.screen
            await pilot.press("e")
            await pilot.pause()
            self.assertFalse(screen._editing)

            await pilot.press("O")
            await pilot.pause()
            await pilot.press("e")
            await pilot.pause()
            self.assertTrue(screen._editing)

    async def test_empty_delete_reason_keeps_the_row(self) -> None:
        async with self.app.run_test(size=(120, 40)) as pilot:
            await settle(pilot)
            self.app.override_mode = True
            self.app.selected = ("task", self.task.id)
            await _palette(pilot, "delete")
            from lazyplan.presentation.tui.screens import FilterPromptScreen

            await pilot.click("#ok")
            await pilot.pause()
            self.assertIsInstance(self.app.screen, FilterPromptScreen)
            await pilot.press("enter")
            await pilot.pause()
            self.assertIsNotNone(Store(self.db).get_task(self.task.id))
            self.assertEqual(
                [event for event in Store(self.db).feed() if event["kind"] == "override"],
                [],
            )

    async def test_force_claim_requires_and_records_a_reason(self) -> None:
        from lazyplan.presentation.tui.screens import FilterPromptScreen

        Store(self.db).claim_task(self.task.id, "alice", 300)
        async with self.app.run_test(size=(120, 40)) as pilot:
            await settle(pilot)
            self.app.override_mode = True
            self.app.selected = ("task", self.task.id)
            await _palette(pilot, "force release")
            self.assertIsInstance(self.app.screen, FilterPromptScreen)
            await pilot.press("enter")
            await pilot.pause()
            self.assertIsNotNone(Store(self.db).get_claim(self.task.id))

            await _palette(pilot, "force release")
            for char in "takeover":
                await pilot.press(char)
            await pilot.press("enter")
            await pilot.pause()
            self.assertIsNone(Store(self.db).get_claim(self.task.id))
            events = [event for event in Store(self.db).feed() if event["kind"] == "override"]
            self.assertTrue(
                any(
                    event["action"] == "claim force release" and "takeover" in event["detail"]
                    for event in events
                )
            )


if __name__ == "__main__":
    unittest.main()
