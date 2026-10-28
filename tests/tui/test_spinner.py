"""Doing rows animate through the design spinner without a tree rebuild."""

import os
import tempfile
import unittest
from unittest import mock

from lazyplan import design, services
from lazyplan.models import Status
from lazyplan.store import Store
from tests.support.pilot import settle

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

            await settle(pilot)
            self.app.selected = ("task", self.doing)
            self.app.update_preview()
            await pilot.pause()
            from textual.widgets import Static

            preview_before = str(self.app.query_one("#preview-body", Static).render())
            selected_before = self.app.selected
            folds_before = (set(self.app._expanded), set(self.app._collapsed))
            rows_before = set(self.app._row_nodes)

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
            self.assertEqual(set(self.app._row_nodes), rows_before)
            self.assertEqual(self.app.selected, selected_before)
            self.assertEqual((set(self.app._expanded), set(self.app._collapsed)), folds_before)
            preview_after = str(self.app.query_one("#preview-body", Static).render())
            self.assertEqual(preview_after, preview_before)

    async def test_idle_until_a_doing_row_appears(self):
        path = os.path.join(self.tmp.name, "idle.db")
        store = Store(path)
        pid = store.add_plan("Plan").id
        sid = store.add_milestone(pid, "Milestone").id
        tid = store.add_task(sid, "Todo task").id
        app = tui_mod.create_app(path)
        async with app.run_test() as pilot:
            await pilot.pause()
            if app._spinner_timer is not None:
                app._spinner_timer.pause()
            self.assertEqual(app._spinner_rows, {})
            before = {key: str(node.label) for key, node in app._row_nodes.items()}
            app._spin()
            self.assertEqual(app._spinner_tick, 0)
            self.assertEqual(
                {key: str(node.label) for key, node in app._row_nodes.items()},
                before,
            )

            services.set_status(store, "task", tid, Status.DOING)
            app.refresh_all()
            await pilot.pause()
            self.assertIn(("task", tid), app._spinner_rows)
            app._spin()
            self.assertEqual(str(app._row_nodes[("task", tid)].label)[0], "◓")

    async def test_opt_out_keeps_the_static_glyph(self):
        with mock.patch.dict(os.environ, {"LAZYPLAN_NO_SPINNER": "1"}):
            app = tui_mod.create_app(self.db)
            async with app.run_test() as pilot:
                await pilot.pause()
                self.assertFalse(app._spinner_enabled)
                self.assertIsNone(app._spinner_timer)
                label = str(app._row_nodes[("task", self.doing)].label)
                self.assertEqual(label[0], "◐")
                app._spin()
                self.assertEqual(app._spinner_tick, 0)
                self.assertEqual(str(app._row_nodes[("task", self.doing)].label), label)
