"""Tree folding: z/Z collapse, state survives refresh, space still cycles status.

Headless Textual pilot tests (skipped on stdlib-only interpreters).
Covers the space-shadowing regression: the native Tree space-toggle is
dropped so app-level `space` always cycles status.
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


@unittest.skipUnless(tui_mod is not None and tui_mod._TEXTUAL_OK, "textual not installed")
class TestTreeFold(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "t.db")
        store = Store(self.db)
        self.pid = store.add_project("P").id
        self.sid = store.add_story(self.pid, "S").id
        self.bare_sid = store.add_story(self.pid, "Bare").id
        store.add_task(self.sid, "T1")
        store.add_task(self.sid, "T2")
        self.store = Store(self.db)
        self.app = tui_mod.create_app(self.db)

    async def asyncTearDown(self):
        self.tmp.cleanup()

    def _nodes(self):
        return (
            self.app._row_nodes[("project", self.pid)],
            self.app._row_nodes[("story", self.sid)],
        )

    async def test_space_cycles_status_on_project(self):
        from textual.widgets import Tree

        async with self.app.run_test() as pilot:
            await pilot.pause()
            tree = self.app.query_one("#tree", Tree)
            tree.move_cursor(self.app._row_nodes[("project", self.pid)])
            await pilot.pause()
            await pilot.press("space")
            await pilot.pause()
            self.assertEqual(self.store.get_project(self.pid).status.value, "doing")
            proj, _ = self._nodes()
            self.assertTrue(proj.is_expanded)

    async def test_space_cycles_status_on_story(self):
        from textual.widgets import Tree

        async with self.app.run_test() as pilot:
            await pilot.pause()
            tree = self.app.query_one("#tree", Tree)
            tree.move_cursor(self.app._row_nodes[("story", self.sid)])
            await pilot.pause()
            await pilot.press("space")
            await pilot.pause()
            self.assertEqual(self.store.get_story(self.sid).status.value, "doing")

    async def test_z_folds_selected_story(self):
        from textual.widgets import Tree

        async with self.app.run_test() as pilot:
            await pilot.pause()
            tree = self.app.query_one("#tree", Tree)
            tree.move_cursor(self.app._row_nodes[("story", self.sid)])
            await pilot.pause()
            self.assertNotIn(("story", self.sid), self.app._collapsed)
            await pilot.press("z")
            await pilot.pause()
            _, story = self._nodes()
            self.assertFalse(story.is_expanded)
            self.assertIn(("story", self.sid), self.app._collapsed)
            await pilot.press("z")
            await pilot.pause()
            _, story = self._nodes()
            self.assertTrue(story.is_expanded)
            self.assertNotIn(("story", self.sid), self.app._collapsed)

    async def test_taskless_story_has_no_fold(self):
        async with self.app.run_test() as pilot:
            await pilot.pause()
            bare = self.app._row_nodes[("story", self.bare_sid)]
            self.assertFalse(bare.allow_expand)

    async def test_fold_all_toggles(self):
        from textual.widgets import Tree

        async with self.app.run_test() as pilot:
            await pilot.pause()
            tree = self.app.query_one("#tree", Tree)
            tree.move_cursor(self.app._row_nodes[("project", self.pid)])
            await pilot.pause()
            await pilot.press("Z")
            await pilot.pause()
            proj, story = self._nodes()
            self.assertFalse(proj.is_expanded)
            self.assertFalse(story.is_expanded)
            await pilot.press("Z")
            await pilot.pause()
            proj, story = self._nodes()
            self.assertTrue(proj.is_expanded)
            self.assertTrue(story.is_expanded)

    async def test_fold_survives_refresh(self):
        from textual.widgets import Tree

        async with self.app.run_test() as pilot:
            await pilot.pause()
            tree = self.app.query_one("#tree", Tree)
            tree.move_cursor(self.app._row_nodes[("project", self.pid)])
            await pilot.pause()
            await pilot.press("z")
            await pilot.pause()
            self.app.refresh_all("probe")
            await pilot.pause()
            proj, _ = self._nodes()
            self.assertFalse(proj.is_expanded)
            self.assertIn(("project", self.pid), self.app._collapsed)

    async def test_left_collapses_header(self):
        from textual.widgets import Tree

        async with self.app.run_test() as pilot:
            await pilot.pause()
            tree = self.app.query_one("#tree", Tree)
            tree.move_cursor(self.app._row_nodes[("project", self.pid)])
            await pilot.pause()
            await pilot.press("left")
            await pilot.pause()
            proj, _ = self._nodes()
            self.assertFalse(proj.is_expanded)
            self.assertIn(("project", self.pid), self.app._collapsed)

    async def test_left_on_folded_story_jumps_to_parent(self):
        from textual.widgets import Tree

        async with self.app.run_test() as pilot:
            await pilot.pause()
            tree = self.app.query_one("#tree", Tree)
            tree.move_cursor(self.app._row_nodes[("story", self.sid)])
            await pilot.pause()
            await pilot.press("z")
            await pilot.pause()
            tree.move_cursor(self.app._row_nodes[("story", self.sid)])
            await pilot.pause()
            await pilot.press("left")
            await pilot.pause()
            cursor = tree.cursor_node
            self.assertIsNotNone(cursor)
            assert cursor is not None
            self.assertEqual(getattr(cursor, "data", {}).get("kind"), "project")
            self.assertEqual(getattr(cursor, "data", {}).get("id"), self.pid)

    async def test_right_expands_header(self):
        from textual.widgets import Tree

        async with self.app.run_test() as pilot:
            await pilot.pause()
            tree = self.app.query_one("#tree", Tree)
            tree.move_cursor(self.app._row_nodes[("project", self.pid)])
            await pilot.pause()
            await pilot.press("left")
            await pilot.pause()
            tree.move_cursor(self.app._row_nodes[("project", self.pid)])
            await pilot.pause()
            await pilot.press("right")
            await pilot.pause()
            proj, _ = self._nodes()
            self.assertTrue(proj.is_expanded)
            self.assertNotIn(("project", self.pid), self.app._collapsed)

    async def test_right_on_open_story_jumps_to_first_task(self):
        from textual.widgets import Tree

        async with self.app.run_test() as pilot:
            await pilot.pause()
            tree = self.app.query_one("#tree", Tree)
            tree.move_cursor(self.app._row_nodes[("story", self.sid)])
            await pilot.pause()
            await pilot.press("right")
            await pilot.pause()
            cursor = tree.cursor_node
            self.assertIsNotNone(cursor)
            assert cursor is not None
            self.assertEqual(getattr(cursor, "data", {}).get("kind"), "task")

    async def test_arrows_noop_outside_tree(self):
        from textual.widgets import Tree  # noqa: F401

        async with self.app.run_test() as pilot:
            await pilot.pause()
            self.app.action_view_gantt()
            await pilot.pause()
            await pilot.press("left")
            await pilot.press("right")
            await pilot.pause()
            self.assertEqual(self.app.mode, "gantt")
            self.assertEqual(self.app._collapsed, set())

    def test_help_mentions_fold(self):
        self.assertIn("z/Z fold one/all", design.HELP_TEXT)
        self.assertIn("left/right collapse/expand", design.HELP_TEXT)


if __name__ == "__main__":
    unittest.main()
