"""External-change polling: heartbeats, structural edits, and rebuild counts."""

from __future__ import annotations

import os
import tempfile
import unittest

from lazyplan.store import Store

try:
    from textual.widgets import Static, Tree

    from lazyplan.presentation.tui import create_app
except ImportError:  # pragma: no cover - textual not installed
    create_app = None  # type: ignore[assignment]


class PollHarness:
    """One open session plus a hand-driven external-change poll.

    The app's own one-second timer is never waited on: tests call `poll()`
    after each database write so a heartbeat or edit is observed at a known
    point in time.
    """

    def __init__(self, app: object, store: Store, session_id: int) -> None:
        self.app = app
        self.store = store
        self.session_id = session_id

    def poll(self) -> None:
        """Run exactly one external-change poll."""
        self.app.tree_controller.poll()  # type: ignore[attr-defined]

    def heartbeat(self, phase: str = "working") -> None:
        """Touch the open session, then poll once."""
        self.store.touch_session(self.session_id, phase=phase)
        self.poll()

    @property
    def rebuilds(self) -> int:
        """How many full tree rebuilds the controller has run."""
        return int(self.app.tree_controller.rebuilds)  # type: ignore[attr-defined]


@unittest.skipUnless(create_app is not None, "textual not installed")
class RefreshCase(unittest.IsolatedAsyncioTestCase):
    """A mounted app with one plan, milestone, and task."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(os.path.join(self.tmp.name, "refresh.db"))
        self.plan = self.store.add_plan("Plan")
        self.milestone = self.store.add_milestone(self.plan.id, "Milestone")
        self.task = self.store.add_task(self.milestone.id, "Task")

    def open_session(self) -> int:
        session, _ = self.store.start_session("ana", plan_id=self.plan.id)
        return session.id

    def harness(self, app: object, session_id: int) -> PollHarness:
        return PollHarness(app, self.store, session_id)

    def row_ids(self, app: object) -> dict[tuple[str, int], int]:
        return {key: id(node) for key, node in app._row_nodes.items()}  # type: ignore[attr-defined]


class TestHeartbeatKeepsTreeStill(RefreshCase):
    async def test_five_heartbeats_leave_nodes_cursor_and_scroll_still(self) -> None:
        for index in range(8):
            self.store.add_plan(f"Extra {index}")
        session_id = self.open_session()
        app = create_app(self.store.path)
        async with app.run_test(size=(120, 24)) as pilot:
            await pilot.pause()
            harness = self.harness(app, session_id)
            tree = app.query_one("#tree", Tree)
            tree.move_cursor(next(reversed(list(app._row_nodes.values()))))
            tree.scroll_to(y=4, animate=False)
            await pilot.pause()
            nodes = self.row_ids(app)
            cursor_line = tree.cursor_line
            scroll = tree.scroll_offset
            rebuilds = harness.rebuilds
            for phase in ("working", "awaiting", "working", "awaiting", "working"):
                harness.heartbeat(phase)
                await pilot.pause()
            self.assertEqual(harness.rebuilds, rebuilds)
            self.assertEqual(self.row_ids(app), nodes)
            self.assertEqual(tree.cursor_line, cursor_line)
            self.assertEqual(tree.scroll_offset, scroll)

    async def test_the_agents_pane_follows_working_and_awaiting(self) -> None:
        session_id = self.open_session()
        app = create_app(self.store.path)
        async with app.run_test(size=(120, 24)) as pilot:
            await pilot.pause()
            harness = self.harness(app, session_id)
            body = app.query_one("#agents-body", Static)
            harness.heartbeat("working")
            await pilot.pause()
            self.assertIn("working", str(body.content))
            harness.heartbeat("awaiting")
            await pilot.pause()
            self.assertIn("awaiting you", str(body.content))

    async def test_a_structural_edit_still_rebuilds(self) -> None:
        session_id = self.open_session()
        app = create_app(self.store.path)
        async with app.run_test(size=(120, 24)) as pilot:
            await pilot.pause()
            harness = self.harness(app, session_id)
            before = harness.rebuilds
            self.store.update_task(self.task.id, title="Renamed", actor="ana")
            harness.poll()
            self.assertEqual(harness.rebuilds - before, 1)


if __name__ == "__main__":
    unittest.main()
