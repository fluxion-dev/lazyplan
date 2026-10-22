"""Tree folding: modal palette folds, state survives refresh, space is parked.

Headless Textual pilot tests (skipped on stdlib-only interpreters).
Minimal keys own the tree (j/k, arrows, enter, esc, c); every mutation
runs through the modal palette.
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from lazyplan import design
from lazyplan.store import Store

try:
    from lazyplan import tui as tui_mod
except ImportError:  # stdlib-only interpreter: no textual, no screens
    tui_mod = None  # type: ignore[assignment]


async def _palette(pilot, query: str) -> None:
    """Drive the modal palette: open with c, type query, run first match."""
    await pilot.press("c")
    await pilot.pause()
    for ch in query:
        await pilot.press(ch)
    await pilot.pause()
    await pilot.press("enter")
    await pilot.pause()
    await pilot.pause()


@unittest.skipUnless(tui_mod is not None and tui_mod._TEXTUAL_OK, "textual not installed")
class TestTreeFold(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "t.db")
        store = Store(self.db)
        self.pid = store.add_plan("P").id
        self.sid = store.add_milestone(self.pid, "S").id
        self.bare_sid = store.add_milestone(self.pid, "Bare").id
        store.add_task(self.sid, "T1")
        store.add_task(self.sid, "T2")
        self.store = Store(self.db)
        self.app = tui_mod.create_app(self.db)

    async def asyncTearDown(self):
        self.tmp.cleanup()

    def _nodes(self):
        return (
            self.app._row_nodes[("plan", self.pid)],
            self.app._row_nodes[("milestone", self.sid)],
        )

    async def test_space_cycles_status_on_plan(self):
        from textual.widgets import Tree

        async with self.app.run_test() as pilot:
            await pilot.pause()
            tree = self.app.query_one("#tree", Tree)
            tree.move_cursor(self.app._row_nodes[("plan", self.pid)])
            await pilot.pause()
            await pilot.press("space")
            await pilot.pause()
            # space is parked: nothing happens without the palette
            self.assertEqual(self.store.get_plan(self.pid).status.value, "todo")
            await _palette(pilot, "cycle status")
            # children still open: rollup heals the palette cycle back to todo
            self.assertEqual(self.store.get_plan(self.pid).status.value, "todo")
            proj, _ = self._nodes()
            self.assertTrue(proj.is_expanded)

    async def test_space_cycles_status_on_milestone(self):
        from textual.widgets import Tree

        async with self.app.run_test() as pilot:
            await pilot.pause()
            tree = self.app.query_one("#tree", Tree)
            tree.move_cursor(self.app._row_nodes[("milestone", self.sid)])
            await pilot.pause()
            await pilot.press("space")
            await pilot.pause()
            # space is parked: nothing happens without the palette
            self.assertEqual(self.store.get_milestone(self.sid).status.value, "todo")
            await _palette(pilot, "cycle status")
            # tasks still open: rollup heals the palette cycle back to todo
            self.assertEqual(self.store.get_milestone(self.sid).status.value, "todo")

    async def test_space_cycles_childless_milestone(self):
        from textual.widgets import Tree

        async with self.app.run_test() as pilot:
            await pilot.pause()
            tree = self.app.query_one("#tree", Tree)
            tree.move_cursor(self.app._row_nodes[("milestone", self.bare_sid)])
            await pilot.pause()
            await pilot.press("space")
            await pilot.pause()
            # space is parked: nothing happens without the palette
            self.assertEqual(self.store.get_milestone(self.bare_sid).status.value, "todo")
            await _palette(pilot, "cycle status")
            self.assertEqual(self.store.get_milestone(self.bare_sid).status.value, "doing")

    def test_tui_starts_unfiltered(self):
        self.assertIsNone(self.app.status_filter)

    async def test_single_click_selects_without_dialog(self):
        async with self.app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            tid = Store(self.db).list_tasks(self.sid)[0].id
            await pilot.click("#tree", offset=(10, 3))
            await pilot.pause()
            self.assertEqual(len(self.app.screen_stack), 1)
            self.assertEqual(self.app.selected, ("task", tid))

    async def test_double_click_opens_detail(self):
        from unittest import mock

        from lazyplan.screens import DetailScreen

        async with self.app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            with mock.patch.object(tui_mod, "DOUBLE_CLICK_WINDOW", 30.0):
                await pilot.click("#tree", offset=(10, 3))
                await pilot.pause()
                await pilot.click("#tree", offset=(10, 3))
                await pilot.pause()
            self.assertEqual(len(self.app.screen_stack), 2)
            self.assertIsInstance(self.app.screen, DetailScreen)

    async def test_slow_clicks_do_not_open(self):
        import asyncio

        async with self.app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.click("#tree", offset=(10, 3))
            await pilot.pause()
            await asyncio.sleep(0.6)
            await pilot.click("#tree", offset=(10, 3))
            await pilot.pause()
            self.assertEqual(len(self.app.screen_stack), 1)

    async def test_enter_opens_detail(self):
        from textual.widgets import Tree

        from lazyplan.screens import DetailScreen

        async with self.app.run_test() as pilot:
            await pilot.pause()
            tree = self.app.query_one("#tree", Tree)
            tree.move_cursor(self.app._row_nodes[("milestone", self.sid)])
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            self.assertEqual(len(self.app.screen_stack), 2)
            self.assertIsInstance(self.app.screen, DetailScreen)

    def test_note_click_window(self):
        self.assertFalse(self.app.note_click(("task", 1)))
        self.assertTrue(self.app.note_click(("task", 1)))
        self.app._last_click_at -= 1.0
        self.assertFalse(self.app.note_click(("task", 1)))
        self.assertFalse(self.app.note_click(("task", 2)))

    async def test_z_folds_selected_milestone(self):
        from textual.widgets import Tree

        async with self.app.run_test() as pilot:
            await pilot.pause()
            tree = self.app.query_one("#tree", Tree)
            tree.move_cursor(self.app._row_nodes[("milestone", self.sid)])
            await pilot.pause()
            self.assertNotIn(("milestone", self.sid), self.app._collapsed)
            await _palette(pilot, "fold one")
            _, milestone = self._nodes()
            self.assertFalse(milestone.is_expanded)
            self.assertIn(("milestone", self.sid), self.app._collapsed)
            await _palette(pilot, "fold one")
            _, milestone = self._nodes()
            self.assertTrue(milestone.is_expanded)
            self.assertNotIn(("milestone", self.sid), self.app._collapsed)

    async def test_taskless_milestone_has_no_fold(self):
        async with self.app.run_test() as pilot:
            await pilot.pause()
            bare = self.app._row_nodes[("milestone", self.bare_sid)]
            self.assertFalse(bare.allow_expand)

    async def test_fold_all_toggles(self):
        from textual.widgets import Tree

        async with self.app.run_test() as pilot:
            await pilot.pause()
            tree = self.app.query_one("#tree", Tree)
            tree.move_cursor(self.app._row_nodes[("plan", self.pid)])
            await pilot.pause()
            await _palette(pilot, "fold all")
            proj, milestone = self._nodes()
            self.assertFalse(proj.is_expanded)
            self.assertFalse(milestone.is_expanded)
            await _palette(pilot, "fold all")
            proj, milestone = self._nodes()
            self.assertTrue(proj.is_expanded)
            self.assertTrue(milestone.is_expanded)

    async def test_fold_survives_refresh(self):
        from textual.widgets import Tree

        async with self.app.run_test() as pilot:
            await pilot.pause()
            tree = self.app.query_one("#tree", Tree)
            tree.move_cursor(self.app._row_nodes[("plan", self.pid)])
            await pilot.pause()
            await _palette(pilot, "fold one")
            self.app.refresh_all("probe")
            await pilot.pause()
            proj, _ = self._nodes()
            self.assertFalse(proj.is_expanded)
            self.assertIn(("plan", self.pid), self.app._collapsed)

    async def test_left_collapses_header(self):
        from textual.widgets import Tree

        async with self.app.run_test() as pilot:
            await pilot.pause()
            tree = self.app.query_one("#tree", Tree)
            tree.move_cursor(self.app._row_nodes[("plan", self.pid)])
            await pilot.pause()
            await pilot.press("left")
            await pilot.pause()
            proj, _ = self._nodes()
            self.assertFalse(proj.is_expanded)
            self.assertIn(("plan", self.pid), self.app._collapsed)

    async def test_left_on_folded_milestone_jumps_to_parent(self):
        from textual.widgets import Tree

        async with self.app.run_test() as pilot:
            await pilot.pause()
            tree = self.app.query_one("#tree", Tree)
            tree.move_cursor(self.app._row_nodes[("milestone", self.sid)])
            await pilot.pause()
            await _palette(pilot, "fold one")
            tree.move_cursor(self.app._row_nodes[("milestone", self.sid)])
            await pilot.pause()
            await pilot.press("left")
            await pilot.pause()
            cursor = tree.cursor_node
            self.assertIsNotNone(cursor)
            assert cursor is not None
            self.assertEqual(getattr(cursor, "data", {}).get("kind"), "plan")
            self.assertEqual(getattr(cursor, "data", {}).get("id"), self.pid)

    async def test_right_expands_header(self):
        from textual.widgets import Tree

        async with self.app.run_test() as pilot:
            await pilot.pause()
            tree = self.app.query_one("#tree", Tree)
            tree.move_cursor(self.app._row_nodes[("plan", self.pid)])
            await pilot.pause()
            await pilot.press("left")
            await pilot.pause()
            tree.move_cursor(self.app._row_nodes[("plan", self.pid)])
            await pilot.pause()
            await pilot.press("right")
            await pilot.pause()
            proj, _ = self._nodes()
            self.assertTrue(proj.is_expanded)
            self.assertNotIn(("plan", self.pid), self.app._collapsed)

    async def test_right_on_open_milestone_jumps_to_first_task(self):
        from textual.widgets import Tree

        async with self.app.run_test() as pilot:
            await pilot.pause()
            tree = self.app.query_one("#tree", Tree)
            tree.move_cursor(self.app._row_nodes[("milestone", self.sid)])
            await pilot.pause()
            await pilot.press("right")
            await pilot.pause()
            cursor = tree.cursor_node
            self.assertIsNotNone(cursor)
            assert cursor is not None
            self.assertEqual(getattr(cursor, "data", {}).get("kind"), "task")

    async def test_arrows_noop_without_selection(self):
        async with self.app.run_test() as pilot:
            await pilot.pause()
            self.app.selected = None
            await pilot.pause()
            await pilot.press("left")
            await pilot.press("right")
            await pilot.pause()
            self.assertEqual(self.app._collapsed, set())

    async def test_statusbar_shows_queue_counts(self):
        from textual.widgets import Label

        async with self.app.run_test() as pilot:
            await pilot.pause()
            bar = self.app.query_one("#status", Label)
            self.assertIn("Q:1/0/0", str(bar.content))

    def test_help_mentions_fold(self):
        self.assertIn("fold", design.HELP_TEXT)
        self.assertIn("left/right", design.HELP_TEXT)


@unittest.skipUnless(tui_mod is not None and tui_mod._TEXTUAL_OK, "textual not installed")
class TestDoneCollapsed(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "t.db")
        store = Store(self.db)
        self.did = store.add_plan("Done").id
        dsid = store.add_milestone(self.did, "DS").id
        dtid = store.add_task(dsid, "DT").id
        from lazyplan import services
        from lazyplan.models import Status

        services.set_status(store, "task", dtid, Status.DONE)
        self.oid = store.add_plan("Open").id
        store.add_milestone(self.oid, "OS")
        self.app = tui_mod.create_app(self.db)

    async def asyncTearDown(self):
        self.tmp.cleanup()

    async def test_done_plan_collapsed_open_expanded(self):
        async with self.app.run_test() as pilot:
            await pilot.pause()
            self.assertFalse(self.app._row_nodes[("plan", self.did)].is_expanded)
            self.assertTrue(self.app._row_nodes[("plan", self.oid)].is_expanded)

    async def test_manual_expand_survives_refresh(self):
        from textual.widgets import Tree

        async with self.app.run_test() as pilot:
            await pilot.pause()
            tree = self.app.query_one("#tree", Tree)
            tree.move_cursor(self.app._row_nodes[("plan", self.did)])
            await pilot.pause()
            await _palette(pilot, "fold one")
            self.assertTrue(self.app._row_nodes[("plan", self.did)].is_expanded)
            self.app.refresh_all("")
            await pilot.pause()
            self.assertTrue(self.app._row_nodes[("plan", self.did)].is_expanded)

    async def test_z_refolds_expanded_done(self):
        from textual.widgets import Tree

        async with self.app.run_test() as pilot:
            await pilot.pause()
            tree = self.app.query_one("#tree", Tree)
            tree.move_cursor(self.app._row_nodes[("plan", self.did)])
            await pilot.pause()
            await _palette(pilot, "fold one")  # expand
            await _palette(pilot, "fold one")  # refold
            self.assertFalse(self.app._row_nodes[("plan", self.did)].is_expanded)


@unittest.skipUnless(tui_mod is not None and tui_mod._TEXTUAL_OK, "textual not installed")
class TestShowAllToggle(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "t.db")
        store = Store(self.db)
        for i in range(7):
            store.add_plan(f"P{i}")
        self.store = Store(self.db)
        self.app = tui_mod.create_app(self.db)

    async def asyncTearDown(self):
        self.tmp.cleanup()

    def _plan_rows(self):
        return [k for k in self.app._row_nodes if k[0] == "plan"]

    async def test_capped_by_default_toggle_shows_all_and_back(self):
        async with self.app.run_test() as pilot:
            await pilot.pause()
            self.assertEqual(len(self._plan_rows()), 5)
            await _palette(pilot, "show all")
            self.assertEqual(len(self._plan_rows()), 7)
            await _palette(pilot, "show all")
            self.assertEqual(len(self._plan_rows()), 5)


if __name__ == "__main__":
    unittest.main()
