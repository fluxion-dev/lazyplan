"""Link and unlink external references from the screen."""

from __future__ import annotations

import os
import tempfile
import unittest

from lazyplan.store import Store

try:
    from textual.widgets import Input

    from lazyplan.presentation import tui as tui_mod
    from lazyplan.presentation.tui.screens import FilterPromptScreen, RefScreen
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
class ReferenceActionsTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "refs.db")
        store = Store(self.db)
        self.plan = store.add_plan("Ref plan", "What", goal="Why")
        self.store = store
        self.app = tui_mod.create_app(self.db)
        self.app.override_mode = True

    async def asyncTearDown(self) -> None:
        self.tmp.cleanup()

    async def test_link_and_unlink_a_reference(self) -> None:
        async with self.app.run_test(size=(120, 40)) as pilot:
            await settle(pilot)
            self.app.selected = ("plan", self.plan.id)
            await _palette(pilot, "link external")
            self.assertIsInstance(self.app.screen, RefScreen)
            self.app.screen.query_one("#r-url", Input).value = "https://example.com/epic"
            self.app.screen.query_one("#r-title", Input).value = "Epic"
            await pilot.click("#ok")
            await pilot.pause()
            refs = Store(self.db).list_refs(self.plan.id)
            self.assertEqual(len(refs), 1)
            self.assertEqual(refs[0].url, "https://example.com/epic")
            events = [event for event in Store(self.db).feed() if event["kind"] == "override"]
            self.assertTrue(any(event["action"] == "ref link" for event in events))

            await _palette(pilot, "unlink external")
            self.assertIsInstance(self.app.screen, FilterPromptScreen)
            for char in "https://example.com/epic":
                await pilot.press(char)
            await pilot.press("enter")
            await pilot.pause()
            self.assertEqual(Store(self.db).list_refs(self.plan.id), [])
            events = [event for event in Store(self.db).feed() if event["kind"] == "override"]
            self.assertTrue(any(event["action"] == "ref unlink" for event in events))


if __name__ == "__main__":
    unittest.main()
