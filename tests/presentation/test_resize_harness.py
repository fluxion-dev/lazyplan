"""The resize matrix harness reads one surface at every supported size.

This is the harness proof: the main shell and one trust hub walk all four
sizes, record regions, content, selection, and scroll, and keep their state.
Every surface suite builds on :mod:`tests.support.resize`.
"""

from __future__ import annotations

import os
import tempfile
import unittest

from lazyplan.store import Store

try:
    from textual.widgets import Static

    from lazyplan.presentation.tui import create_app
    from lazyplan.presentation.tui.screens.hub_kinds import CriteriaHub
except ImportError:  # pragma: no cover - textual not installed
    Static = None  # type: ignore[assignment,misc]
    create_app = None  # type: ignore[assignment]
    CriteriaHub = None  # type: ignore[assignment]

from tests.support.resize import SIZES, ResizeMatrix

SHELL_PARTS = {
    "plans-active": "#plans-active",
    "agents": "#agents",
    "plans-finished": "#plans-finished",
    "git": "#git",
    "preview": "#preview",
    "metrics": "#metrics",
    "hints": "#hints",
}
SHELL_SIBLINGS = ("plans-active", "agents", "plans-finished", "git")
HUB_PARTS = {
    "page": "#hub-page",
    "list": "#hub-list-wrap",
    "preview": "#hub-preview",
    "hints": "#hub-hints",
}


@unittest.skipUnless(create_app is not None, "textual not installed")
class ResizeHarnessTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(os.path.join(self.tmp.name, "resize.db"))
        self.plan = self.store.add_plan(
            "Resize every panel",
            "The shell reflows on resize.",
            goal="A narrow terminal keeps every panel readable.",
        )
        self.milestone = self.store.add_milestone(self.plan.id, "Measure", "Record each size.")
        self.store.add_task(self.milestone.id, "Walk the matrix", "Four sizes, one mount.")
        self.store.add_criteria("plan", self.plan.id, "Every panel reflows", actor="fixture")

    async def test_the_shell_walks_every_size_without_losing_state(self) -> None:
        app = create_app(str(self.store.path))
        async with app.run_test(size=SIZES[0]) as pilot:
            await pilot.pause()
            app.select_row("plan", self.plan.id)
            await pilot.pause()
            selected = app.selected
            rows = len(app._row_specs)
            matrix = await ResizeMatrix("shell").walk(
                pilot,
                parts=SHELL_PARTS,
                selection=lambda: app.selected,
                scrolls=("#preview-scroll",),
            )
            self.assertEqual(matrix.sizes(), SIZES)
            for snapshot in matrix.snapshots:
                with self.subTest(size=snapshot.size):
                    snapshot.assert_inside(self)
                    snapshot.assert_no_overlap(self, SHELL_SIBLINGS)
                    self.assertEqual(snapshot.selection, selected)
                    self.assertGreater(snapshot.part("hints").region[2], 0)
                    if snapshot.part("preview").region is not None:
                        self.assertGreater(snapshot.part("preview").region[3], 0)
            self.assertEqual(app.selected, selected)
            self.assertEqual(len(app._row_specs), rows)

    async def test_a_hub_walks_every_size_and_keeps_its_row(self) -> None:
        app = create_app(str(self.store.path))
        async with app.run_test(size=SIZES[0]) as pilot:
            await pilot.pause()
            hub = CriteriaHub(self.store, "plan", self.plan.id)
            app.push_screen(hub)
            await pilot.pause()
            body = str(hub.query_one("#hub-preview-body", Static).render())
            matrix = await ResizeMatrix("criteria hub").walk(
                pilot,
                parts=HUB_PARTS,
                selection=lambda: hub.query_one("#hub-list").highlighted,
                scrolls=("#hub-preview",),
                cursors=("#hub-list",),
            )
            self.assertEqual(matrix.sizes(), SIZES)
            for snapshot in matrix.snapshots:
                with self.subTest(size=snapshot.size):
                    self.assertEqual(snapshot.selection, 0)
                    self.assertEqual(snapshot.cursor["#hub-list"], 0)
                    self.assertGreater(snapshot.part("hints").region[2], 0)
                    # The split geometry itself is audited in T458 and fixed
                    # with the hub reflow, so the harness only records it here.
                    self.assertIn("list", snapshot.parts)
                    self.assertIn("preview", snapshot.parts)
            self.assertEqual(hub.query_one("#hub-list").highlighted, 0)
            self.assertEqual(str(hub.query_one("#hub-preview-body", Static).render()), body)


if __name__ == "__main__":
    unittest.main()
