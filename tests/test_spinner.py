"""Doing rows animate through the design spinner without a tree rebuild."""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from lazyplan import design, services
from lazyplan.models import Status
from lazyplan.store import Store

try:
    from lazyplan import tui as tui_mod
except ImportError:  # stdlib-only interpreter: no textual, no TUI
    tui_mod = None  # type: ignore[assignment]


@unittest.skipUnless(tui_mod is not None and tui_mod._TEXTUAL_OK, "textual not installed")
class TestSpinner(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "t.db")
        store = Store(self.db)
        self.pid = store.add_plan("Plan").id
        self.sid = store.add_milestone(self.pid, "Milestone").id
        self.doing = store.add_task(self.sid, "Doing task").id
        self.todo = store.add_task(self.sid, "Todo task").id
        self.done = store.add_task(self.sid, "Done task").id
        services.set_status(store, "task", self.doing, Status.DOING)
        services.set_status(store, "task", self.done, Status.DONE)
        self.app = tui_mod.create_app(self.db)

    async def asyncTearDown(self):
        self.tmp.cleanup()

    def _text(self, key: tuple[str, int]) -> str:
        return str(self.app._row_nodes[key].label)

    def _freeze(self) -> None:
        """Take the wall clock out of the test: frames advance by hand."""
        if self.app._spinner_timer is not None:
            self.app._spinner_timer.pause()
        self.app._spinner_tick = 0
        self.app._paint_spinner()

    async def test_doing_rows_cycle_without_rebuilding(self):
        async with self.app.run_test() as pilot:
            await pilot.pause()
            self._freeze()
            keys = [
                ("plan", self.pid),
                ("milestone", self.sid),
                ("task", self.doing),
            ]
            nodes = {key: self.app._row_nodes[key] for key in keys}
            for key in keys:
                self.assertEqual(self._text(key)[0], "◐", key)

            widths = {key: len(self._text(key)) for key in keys}
            tails = {key: self._text(key)[1:] for key in keys}
            frames = []
            for _ in range(len(design.SPINNER_FRAMES)):
                self.app._spin()
                frames.append(self._text(("task", self.doing))[0])
            self.assertEqual(frames, ["◓", "◑", "◒", "◐"])

            for key in keys:
                self.assertIs(self.app._row_nodes[key], nodes[key])
                self.assertEqual(len(self._text(key)), widths[key])
                self.assertEqual(self._text(key)[1:], tails[key])
            self.assertEqual(self._text(("task", self.todo))[0], "○")
            self.assertEqual(self._text(("task", self.done))[0], "●")
