"""Tree behavior: progressive disclosure, folding, selection, and status bar.

Headless Textual pilot tests (skipped on stdlib-only interpreters).
Plans start collapsed; right/`z` reveals milestones, then tasks.
"""

import os
import tempfile
import unittest
from unittest import mock

from lazyplan import design
from lazyplan.store import Store
from tests.support.pilot import settle

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

    async def _select(self, pilot, kind: str, oid: int) -> None:
        from textual.widgets import Tree

        tree = self.app.query_one("#tree", Tree)
        tree.move_cursor(self.app._row_nodes[(kind, oid)])
        await pilot.pause()

    async def _expand(self, pilot, kind: str, oid: int) -> None:
        await self._select(pilot, kind, oid)
        await pilot.press("right")
        await pilot.pause()

    async def test_plans_start_collapsed(self):
        async with self.app.run_test() as pilot:
            await pilot.pause()
            proj, milestone = self._nodes()
            self.assertFalse(proj.is_expanded)
            self.assertFalse(milestone.is_expanded)
            self.assertEqual(self.app._expanded, set())

    async def test_expanding_plan_shows_milestones_not_tasks(self):
        async with self.app.run_test() as pilot:
            await pilot.pause()
            await self._expand(pilot, "plan", self.pid)
            proj, milestone = self._nodes()
            self.assertTrue(proj.is_expanded)
            self.assertFalse(milestone.is_expanded)

    async def test_mount_refreshes_the_tree_once(self):
        calls: list[str] = []
        original = self.app.refresh_all

        def counted(note: str = "") -> None:
            calls.append(note)
            original(note)

        self.app.refresh_all = counted
        async with self.app.run_test() as pilot:
            await pilot.pause()
        self.assertEqual(len(calls), 1)

    async def test_fold_and_mark_do_not_rebuild_the_tree(self):
        async with self.app.run_test() as pilot:
            await pilot.pause()
            await self._expand(pilot, "plan", self.pid)
            with mock.patch.object(self.app, "refresh_all") as refresh:
                await pilot.press("z")
                await pilot.pause()
                self.assertFalse(refresh.called)
                await pilot.press("space")
                await pilot.pause()
                self.assertFalse(refresh.called)
            self.assertIn(("plan", self.pid), self.app.marked)
            self.assertIn("✓", str(self.app._row_nodes[("plan", self.pid)].label))

    async def test_resize_within_a_breakpoint_does_not_rebuild(self):
        async with self.app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            with mock.patch.object(self.app, "refresh_all") as refresh:
                await pilot.resize_terminal(110, 40)
                await pilot.pause()
                self.assertFalse(refresh.called)
                await pilot.resize_terminal(90, 40)
                await pilot.pause()
                self.assertTrue(refresh.called)

    async def test_narrow_hides_preview_and_resize_keeps_selection(self):
        from textual.containers import Horizontal

        async with self.app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            main = self.app.query_one("#main", Horizontal)
            self.assertTrue(main.has_class("narrow"))
            self.assertFalse(self.app.query_one("#preview").display)
            self.assertEqual(self.app.selected, ("plan", self.pid))
            await pilot.resize_terminal(120, 40)
            await pilot.pause()
            self.assertFalse(main.has_class("narrow"))
            self.assertTrue(self.app.query_one("#preview").display)
            self.assertEqual(self.app.selected, ("plan", self.pid))

    async def test_external_change_keeps_folds_and_cursor(self):
        async with self.app.run_test() as pilot:
            await pilot.pause()
            await self._expand(pilot, "plan", self.pid)
            Store(self.db).add_task(self.sid, "Externally added")
            self.app._poll()
            await pilot.pause()
            await pilot.pause()
            self.assertEqual(self.app.selected, ("plan", self.pid))
            self.assertIn(("plan", self.pid), self.app._expanded)

    async def test_space_cycles_status_on_plan(self):
        async with self.app.run_test() as pilot:
            await pilot.pause()
            await self._select(pilot, "plan", self.pid)
            await pilot.press("space")
            await pilot.pause()
            # space is parked: nothing happens without the palette
            self.assertEqual(self.store.get_plan(self.pid).status.value, "todo")
            await _palette(pilot, "cycle status")
            # children still open: rollup heals the palette move back to todo
            self.assertEqual(self.store.get_plan(self.pid).status.value, "todo")

    async def test_space_cycles_status_on_milestone(self):
        async with self.app.run_test() as pilot:
            await pilot.pause()
            await self._expand(pilot, "plan", self.pid)
            await self._select(pilot, "milestone", self.sid)
            await pilot.press("space")
            await pilot.pause()
            self.assertEqual(self.store.get_milestone(self.sid).status.value, "todo")
            await _palette(pilot, "cycle status")
            # tasks still open: rollup heals the palette move back to todo
            self.assertEqual(self.store.get_milestone(self.sid).status.value, "todo")

    async def test_space_cycles_childless_milestone(self):
        async with self.app.run_test() as pilot:
            await pilot.pause()
            await self._expand(pilot, "plan", self.pid)
            await self._select(pilot, "milestone", self.bare_sid)
            await pilot.press("space")
            await pilot.pause()
            self.assertEqual(self.store.get_milestone(self.bare_sid).status.value, "todo")
            await _palette(pilot, "cycle status")
            self.assertEqual(self.store.get_milestone(self.bare_sid).status.value, "doing")

    def test_tui_starts_unfiltered(self):
        self.assertIsNone(self.app.status_filter)

    async def test_single_click_selects_without_dialog(self):
        async with self.app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.click("#tree", offset=(10, 1))
            await pilot.pause()
            self.assertEqual(len(self.app.screen_stack), 1)
            self.assertEqual(self.app.selected, ("plan", self.pid))

    async def test_double_click_opens_detail(self):
        from unittest import mock

        from lazyplan.tui.screens import DetailScreen

        async with self.app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            with mock.patch("lazyplan.tui.actions.DOUBLE_CLICK_WINDOW", 30.0):
                await pilot.click("#tree", offset=(10, 1))
                await pilot.pause()
                await pilot.click("#tree", offset=(10, 1))
                await pilot.pause()
            self.assertEqual(len(self.app.screen_stack), 2)
            self.assertIsInstance(self.app.screen, DetailScreen)

    async def test_slow_clicks_do_not_open(self):
        import asyncio

        async with self.app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.click("#tree", offset=(10, 1))
            await pilot.pause()
            await asyncio.sleep(0.6)
            await pilot.click("#tree", offset=(10, 1))
            await pilot.pause()
            self.assertEqual(len(self.app.screen_stack), 1)

    async def test_enter_opens_detail(self):
        from lazyplan.tui.screens import DetailScreen

        async with self.app.run_test() as pilot:
            await pilot.pause()
            await self._select(pilot, "plan", self.pid)
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

    async def test_e_opens_edit_mode(self):
        from lazyplan.tui.screens import DetailScreen

        async with self.app.run_test() as pilot:
            await pilot.pause()
            await self._select(pilot, "plan", self.pid)
            await pilot.press("e")
            await pilot.pause()
            self.assertIsInstance(self.app.screen, DetailScreen)
            self.assertTrue(self.app.screen._editing)
            self.assertTrue(self.app.screen.query_one("#detail-edit").display)

    async def test_n_on_plan_creates_a_milestone(self):
        from lazyplan.tui.screens import NewMilestoneScreen

        async with self.app.run_test() as pilot:
            await pilot.pause()
            await self._select(pilot, "plan", self.pid)
            await pilot.press("n")
            await pilot.pause()
            self.assertIsInstance(self.app.screen, NewMilestoneScreen)

    async def test_z_folds_selected_milestone(self):
        async with self.app.run_test() as pilot:
            await pilot.pause()
            await self._expand(pilot, "plan", self.pid)
            await self._select(pilot, "milestone", self.sid)
            _, milestone = self._nodes()
            self.assertFalse(milestone.is_expanded)
            await pilot.press("z")
            await pilot.pause()
            _, milestone = self._nodes()
            self.assertTrue(milestone.is_expanded)
            self.assertIn(("milestone", self.sid), self.app._expanded)
            await pilot.press("z")
            await pilot.pause()
            _, milestone = self._nodes()
            self.assertFalse(milestone.is_expanded)
            self.assertNotIn(("milestone", self.sid), self.app._expanded)

    async def test_taskless_milestone_has_no_fold(self):
        async with self.app.run_test() as pilot:
            await pilot.pause()
            bare = self.app._row_nodes[("milestone", self.bare_sid)]
            self.assertFalse(bare.allow_expand)

    async def test_fold_all_toggles(self):
        async with self.app.run_test() as pilot:
            await pilot.pause()
            await _palette(pilot, "fold all")
            proj, milestone = self._nodes()
            self.assertTrue(proj.is_expanded)
            self.assertTrue(milestone.is_expanded)
            await _palette(pilot, "fold all")
            proj, milestone = self._nodes()
            self.assertFalse(proj.is_expanded)
            self.assertFalse(milestone.is_expanded)

    async def test_fold_survives_refresh(self):
        async with self.app.run_test() as pilot:
            await pilot.pause()
            await self._select(pilot, "plan", self.pid)
            await pilot.press("z")
            await pilot.pause()
            self.app.refresh_all("probe")
            await pilot.pause()
            proj, _ = self._nodes()
            self.assertTrue(proj.is_expanded)
            self.assertIn(("plan", self.pid), self.app._expanded)

    async def test_left_collapses_header(self):
        async with self.app.run_test() as pilot:
            await pilot.pause()
            await self._expand(pilot, "plan", self.pid)
            await pilot.press("left")
            await pilot.pause()
            proj, _ = self._nodes()
            self.assertFalse(proj.is_expanded)
            self.assertIn(("plan", self.pid), self.app._collapsed)

    async def test_left_on_folded_milestone_jumps_to_parent(self):
        async with self.app.run_test() as pilot:
            await pilot.pause()
            await self._expand(pilot, "plan", self.pid)
            await self._select(pilot, "milestone", self.sid)
            await pilot.press("left")
            await pilot.pause()
            from textual.widgets import Tree

            cursor = self.app.query_one("#tree", Tree).cursor_node
            self.assertIsNotNone(cursor)
            assert cursor is not None
            self.assertEqual(getattr(cursor, "data", {}).get("kind"), "plan")
            self.assertEqual(getattr(cursor, "data", {}).get("id"), self.pid)

    async def test_right_expands_header(self):
        async with self.app.run_test() as pilot:
            await pilot.pause()
            await self._select(pilot, "plan", self.pid)
            await pilot.press("right")
            await pilot.pause()
            proj, _ = self._nodes()
            self.assertTrue(proj.is_expanded)
            self.assertIn(("plan", self.pid), self.app._expanded)

    async def test_right_on_open_milestone_jumps_to_first_task(self):
        async with self.app.run_test() as pilot:
            await pilot.pause()
            await self._expand(pilot, "plan", self.pid)
            await self._expand(pilot, "milestone", self.sid)
            await pilot.press("right")
            await pilot.pause()
            from textual.widgets import Tree

            cursor = self.app.query_one("#tree", Tree).cursor_node
            self.assertIsNotNone(cursor)
            assert cursor is not None
            self.assertEqual(getattr(cursor, "data", {}).get("kind"), "task")

    async def test_arrows_follow_the_tree_cursor(self):
        async with self.app.run_test() as pilot:
            await pilot.pause()
            await settle(pilot)
            self.app.selected = None
            await pilot.pause()
            await pilot.press("right")
            await pilot.pause()
            proj, _ = self._nodes()
            self.assertTrue(proj.is_expanded)
            self.assertIn(("plan", self.pid), self.app._expanded)
            await pilot.press("left")
            await pilot.pause()
            self.assertFalse(proj.is_expanded)
            self.assertNotIn(("plan", self.pid), self.app._expanded)

    async def test_j_and_k_move_the_cursor(self):
        from textual.widgets import Tree

        async with self.app.run_test() as pilot:
            await pilot.pause()
            await self._expand(pilot, "plan", self.pid)
            await self._select(pilot, "plan", self.pid)
            await pilot.press("j")
            await pilot.pause()
            cursor = self.app.query_one("#tree", Tree).cursor_node
            assert cursor is not None
            self.assertEqual(getattr(cursor, "data", {}).get("kind"), "milestone")
            await pilot.press("k")
            await pilot.pause()
            cursor = self.app.query_one("#tree", Tree).cursor_node
            assert cursor is not None
            self.assertEqual(getattr(cursor, "data", {}).get("kind"), "plan")

    async def test_clicking_the_row_arrow_toggles_the_plan(self):
        async with self.app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            proj, _ = self._nodes()
            self.assertFalse(proj.is_expanded)
            clicked = await pilot.click("#tree", offset=(4, 1))
            await pilot.pause()
            self.assertTrue(clicked)
            self.assertTrue(proj.is_expanded)
            self.assertEqual(len(self.app.screen_stack), 1)
            await pilot.click("#tree", offset=(4, 1))
            await pilot.pause()
            self.assertFalse(proj.is_expanded)
            self.assertEqual(len(self.app.screen_stack), 1)

    async def test_hint_bar_lists_common_keys(self):
        from textual.widgets import Label

        async with self.app.run_test() as pilot:
            await pilot.pause()
            hints = str(self.app.query_one("#hints", Label).content)
            for key in ("n", "e", "s", "x", "d", "/", "?", "c"):
                self.assertIn(key, hints)

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

    async def test_all_plans_start_collapsed(self):
        async with self.app.run_test() as pilot:
            await pilot.pause()
            self.assertFalse(self.app._row_nodes[("plan", self.did)].is_expanded)
            self.assertFalse(self.app._row_nodes[("plan", self.oid)].is_expanded)

    async def test_done_plans_sort_last(self):
        async with self.app.run_test() as pilot:
            await pilot.pause()
            keys = [key for key in self.app._row_nodes if key[0] == "plan"]
            self.assertEqual(keys[-1], ("plan", self.did))

    async def test_manual_expand_survives_refresh(self):
        from textual.widgets import Tree

        async with self.app.run_test() as pilot:
            await pilot.pause()
            tree = self.app.query_one("#tree", Tree)
            tree.move_cursor(self.app._row_nodes[("plan", self.did)])
            await pilot.pause()
            await pilot.press("z")
            await pilot.pause()
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
            await pilot.press("z")  # expand
            await pilot.pause()
            await pilot.press("z")  # refold
            await pilot.pause()
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
