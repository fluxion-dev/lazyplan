"""External-change polling: heartbeats, structural edits, and rebuild counts."""

from __future__ import annotations

import os
import tempfile
import time
import unittest

from lazyplan import services
from lazyplan.core.entities import Status
from lazyplan.store import Store

try:
    from textual.widgets import Static, Tree

    from lazyplan.presentation.tui import create_app
    from lazyplan.presentation.tui.screens.forms import ConfirmScreen
except ImportError:  # pragma: no cover - textual not installed
    create_app = None  # type: ignore[assignment]

COALESCE_PAUSE = 0.35


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
        """Run exactly one external-change poll on the calling thread."""
        self.app.tree_controller.poll_now()  # type: ignore[attr-defined]

    def poll_worker(self) -> None:
        """Start the threaded poll the app's timer uses."""
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

    def expand_all(self, app: object) -> None:
        """Open the fixture plan and milestone so task rows exist."""
        app._expanded.update(  # type: ignore[attr-defined]
            {("plan", self.plan.id), ("milestone", self.milestone.id)}
        )
        app.refresh_all()  # type: ignore[attr-defined]

    def spy_labels(self, app: object) -> list[tuple[str, int]]:
        """Record every set_label call made on the current row nodes."""
        calls: list[tuple[str, int]] = []
        for key, node in app._row_nodes.items():  # type: ignore[attr-defined]
            original = node.set_label

            def spy(label: object, _key: tuple[str, int] = key, _set: object = original) -> None:
                calls.append(_key)
                _set(label)  # type: ignore[operator]

            node.set_label = spy  # type: ignore[method-assign]
        return calls

    def order(self, app: object) -> list[tuple[str, int]]:
        tree = app.query_one("#tree", Tree)  # type: ignore[attr-defined]
        return [key for node in tree.root.children if (key := _node_key(node)) is not None]


def _node_key(node: object) -> tuple[str, int] | None:
    data = getattr(node, "data", None)
    if isinstance(data, dict) and "kind" in data and "id" in data:
        return (str(data["kind"]), int(data["id"]))
    return None


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
            await pilot.pause(COALESCE_PAUSE)
            self.assertEqual(harness.rebuilds - before, 1)


class TestPollScheduling(RefreshCase):
    async def test_a_burst_of_three_writes_makes_one_tree_update(self) -> None:
        session_id = self.open_session()
        app = create_app(self.store.path)
        async with app.run_test(size=(120, 24)) as pilot:
            await pilot.pause()
            harness = self.harness(app, session_id)
            before = harness.rebuilds
            for index in range(3):
                self.store.update_task(self.task.id, title=f"Task {index}", actor="ana")
                harness.poll()
            self.assertEqual(harness.rebuilds, before)
            await pilot.pause(COALESCE_PAUSE)
            self.assertEqual(harness.rebuilds - before, 1)

    async def test_an_open_modal_defers_the_refresh_until_it_closes(self) -> None:
        session_id = self.open_session()
        app = create_app(self.store.path)
        async with app.run_test(size=(120, 24)) as pilot:
            await pilot.pause()
            harness = self.harness(app, session_id)
            app.push_screen(ConfirmScreen("hold"))
            await pilot.pause()
            before = harness.rebuilds
            self.store.update_task(self.task.id, title="While modal", actor="ana")
            harness.poll()
            await pilot.pause(COALESCE_PAUSE)
            self.assertEqual(harness.rebuilds, before)
            self.assertTrue(app._dirty_external)
            app.pop_screen()
            await pilot.pause()
            harness.poll()
            self.assertEqual(harness.rebuilds - before, 1)

    async def test_a_cli_edit_lands_from_the_worker_within_one_second(self) -> None:
        session_id = self.open_session()
        app = create_app(self.store.path)
        async with app.run_test(size=(120, 24)) as pilot:
            await pilot.pause()
            harness = self.harness(app, session_id)
            before = harness.rebuilds
            self.store.update_task(self.task.id, title="From the CLI", actor="ana")
            harness.poll_worker()
            await pilot.pause(COALESCE_PAUSE)
            self.assertEqual(harness.rebuilds - before, 1)


class TestInPlaceReconciliation(RefreshCase):
    async def test_a_task_title_edit_relabels_only_that_row(self) -> None:
        app = create_app(self.store.path)
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            self.expand_all(app)
            await pilot.pause()
            nodes = self.row_ids(app)
            calls = self.spy_labels(app)
            self.store.update_task(self.task.id, title="Renamed", actor="ana")
            app.refresh_all()
            await pilot.pause()
            self.assertEqual(self.row_ids(app), nodes)
            self.assertEqual(calls, [("task", self.task.id)])

    async def test_a_status_move_keeps_node_identity(self) -> None:
        other = self.store.add_plan("Other plan")
        self.store.update_plan(self.plan.id, goal="stays on top", actor="ana")
        app = create_app(self.store.path)
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            self.expand_all(app)
            await pilot.pause()
            nodes = self.row_ids(app)
            other_label = app._row_labels[("plan", other.id)]
            calls = self.spy_labels(app)
            services.cycle_status(self.store, "task", self.task.id, actor="ana")
            app.refresh_all()
            await pilot.pause()
            self.assertEqual(self.row_ids(app), nodes)
            self.assertIn(("task", self.task.id), calls)
            self.assertEqual(app._row_labels[("plan", other.id)], other_label)
            self.assertNotIn(("plan", other.id), calls)

    async def test_a_new_task_appears_without_touching_existing_rows(self) -> None:
        app = create_app(self.store.path)
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            self.expand_all(app)
            await pilot.pause()
            before = self.row_ids(app)
            added = self.store.add_task(self.milestone.id, "Second", actor="ana")
            app.refresh_all()
            await pilot.pause()
            after = self.row_ids(app)
            self.assertEqual(after[("task", self.task.id)], before[("task", self.task.id)])
            self.assertIn(("task", added.id), after)

    async def test_a_removed_task_disappears_without_touching_existing_rows(self) -> None:
        added = self.store.add_task(self.milestone.id, "Second", actor="ana")
        app = create_app(self.store.path)
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            self.expand_all(app)
            await pilot.pause()
            before = self.row_ids(app)
            self.store.delete("task", added.id, actor="ana")
            app.refresh_all()
            await pilot.pause()
            after = self.row_ids(app)
            self.assertNotIn(("task", added.id), after)
            self.assertEqual(after[("task", self.task.id)], before[("task", self.task.id)])

    async def test_a_finished_plan_moves_panels_with_its_expansion(self) -> None:
        app = create_app(self.store.path)
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            self.expand_all(app)
            await pilot.pause()
            services.set_status(
                self.store, "plan", self.plan.id, Status.DONE, actor="ana", heal=False
            )
            app.refresh_all()
            await pilot.pause()
            node = app._row_nodes[("plan", self.plan.id)]
            self.assertIs(node.tree, app.query_one("#tree-finished", Tree))
            self.assertTrue(node.is_expanded)
            self.assertIn(("task", self.task.id), self.row_ids(app))

    async def test_a_reorder_rebuilds_from_the_first_divergence(self) -> None:
        base = time.time()
        plans = [
            self.plan,
            self.store.add_plan("B"),
            self.store.add_plan("C"),
            self.store.add_plan("D"),
        ]
        for plan, offset in zip(plans, (1.0, 0.0, 3.0, 10.0), strict=True):
            self.store.log("ana", "plan", "edit", f"plan #{plan.id} touched", now=base + offset)
        app = create_app(self.store.path)
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            initial = self.order(app)
            self.assertEqual(
                initial,
                [
                    ("plan", plans[3].id),
                    ("plan", plans[2].id),
                    ("plan", plans[0].id),
                    ("plan", plans[1].id),
                ],
            )
            before = self.row_ids(app)
            self.store.log("ana", "plan", "edit", f"plan #{plans[1].id} touched", now=base + 7)
            app.refresh_all()
            await pilot.pause()
            self.assertEqual(
                self.order(app),
                [
                    ("plan", plans[3].id),
                    ("plan", plans[1].id),
                    ("plan", plans[2].id),
                    ("plan", plans[0].id),
                ],
            )
            self.assertEqual(
                self.row_ids(app)[("plan", plans[3].id)], before[("plan", plans[3].id)]
            )


if __name__ == "__main__":
    unittest.main()
