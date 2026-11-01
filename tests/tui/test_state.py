"""AppState routes the public shell fields and query helpers stay narrow."""

from __future__ import annotations

import os
import tempfile
import unittest

from lazyplan.store import Store

try:
    from textual.widgets import Label, Tree

    from lazyplan import tui as tui_mod
    from lazyplan.models import Status
    from lazyplan.tui.query import query_one_opt
    from lazyplan.tui.state import AppState
except ImportError:  # pragma: no cover - stdlib-only interpreter
    tui_mod = None  # type: ignore[assignment]


@unittest.skipUnless(tui_mod is not None and tui_mod._TEXTUAL_OK, "textual not installed")
class StateTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "t.db")
        Store(self.db).add_plan("Plan")

    async def asyncTearDown(self) -> None:
        self.tmp.cleanup()

    def test_state_defaults(self) -> None:
        state = AppState()
        self.assertIsNone(state.selected)
        self.assertIsNone(state.status_filter)
        self.assertFalse(state.show_all)
        self.assertEqual(state.filter_text, "")
        self.assertEqual(state.source_filter, "all")
        self.assertEqual(state.marked, set())
        self.assertEqual(state.expanded, set())
        self.assertEqual(state.collapsed, set())

    async def test_app_properties_route_through_state(self) -> None:
        app = tui_mod.create_app(self.db)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            app.selected = ("plan", 1)
            app.status_filter = Status.DOING
            app.show_all = True
            app.filter_text = "needle"
            app.source_filter = "claims"
            app.marked.add(("plan", 1))
            app._expanded.add(("plan", 1))
            self.assertEqual(app.state.selected, ("plan", 1))
            self.assertEqual(app.state.status_filter, Status.DOING)
            self.assertTrue(app.state.show_all)
            self.assertEqual(app.state.filter_text, "needle")
            self.assertEqual(app.state.source_filter, "claims")
            self.assertIn(("plan", 1), app.state.marked)
            self.assertIn(("plan", 1), app.state.expanded)

    async def test_query_one_opt_handles_absent_and_wrong_type(self) -> None:
        app = tui_mod.create_app(self.db)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            self.assertIsNone(query_one_opt(app, "#missing"))
            self.assertIsNone(query_one_opt(app, "#tree", Label))
            self.assertIsInstance(query_one_opt(app, "#tree", Tree), Tree)


if __name__ == "__main__":
    unittest.main()
