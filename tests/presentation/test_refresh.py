"""External-change polling: heartbeats, structural edits, and rebuild counts."""

from __future__ import annotations

import os
import tempfile
import time
import unittest
from typing import Any
from unittest import mock

from lazyplan import services
from lazyplan.core.entities import Status
from lazyplan.store import Store

try:
    from textual.widgets import Static, Tree

    from lazyplan.presentation.tui import create_app
    from lazyplan.presentation.tui.screens.forms import ConfirmScreen
    from lazyplan.presentation.tui.widgets.preview_panel import PreviewPanel
except ImportError:  # pragma: no cover - textual not installed
    create_app = None  # type: ignore[assignment]

COALESCE_PAUSE = 0.35


class PollHarness:
    """One live agent plus a hand-driven external-change poll.

    The app's own quarter-second timer is never waited on: tests call `poll()`
    after each database write so a transition or edit is observed at a known
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

    def heartbeat(self, status: str = "working") -> None:
        """Move the agent, then poll once."""
        self.store.transition_agent(self.session_id, status, event="test")
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
        agent = self.store.add_agent(
            "ana",
            host="opencode",
            agent="ana",
            plan_id=self.plan.id,
            worktree=self.store.checkout_path(),
        )
        return agent.id

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
            for status in ("working", "waiting", "working", "waiting", "working"):
                harness.heartbeat(status)
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
            harness.heartbeat("waiting")
            await pilot.pause()
            self.assertIn("waiting", str(body.content))
            self.assertNotIn("◆", str(body.content))
            self.assertIn("waiting", str(body.content))

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
    def test_the_background_sweep_runs_every_second(self) -> None:
        from lazyplan.presentation.tui.controllers.poll import SWEEP_INTERVAL

        self.assertEqual(SWEEP_INTERVAL, 1.0)

    async def test_one_sweep_per_second_window(self) -> None:
        app = create_app(self.store.path)
        async with app.run_test(size=(120, 24)) as pilot:
            await pilot.pause()
            controller = app.tree_controller
            controller._last_sweep = 1000.0
            with mock.patch("lazyplan.services.agents.sweep_lost") as sweep:
                with mock.patch(
                    "lazyplan.presentation.tui.controllers.poll.time.time",
                    return_value=1000.5,
                ):
                    controller._read_state()
                self.assertEqual(sweep.call_count, 0)
                with mock.patch(
                    "lazyplan.presentation.tui.controllers.poll.time.time",
                    return_value=1001.0,
                ):
                    controller._read_state()
                self.assertEqual(sweep.call_count, 1)
                with mock.patch(
                    "lazyplan.presentation.tui.controllers.poll.time.time",
                    return_value=1001.5,
                ):
                    controller._read_state()
                self.assertEqual(sweep.call_count, 1)

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


class TestExpansionOwnership(RefreshCase):
    async def test_a_closed_milestone_stays_closed_after_a_structural_write(self) -> None:
        app = create_app(self.store.path)
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            self.expand_all(app)
            await pilot.pause()
            plan_key = ("plan", self.plan.id)
            milestone_key = ("milestone", self.milestone.id)
            app.selected = milestone_key
            app.tree_controller.fold_one()
            await pilot.pause()
            self.assertNotIn(milestone_key, app._expanded)
            expanded = set(app._expanded)
            collapsed = set(app._collapsed)
            self.store.add_task(self.milestone.id, "Second", actor="ana")
            app.refresh_all()
            await pilot.pause()
            self.assertEqual(set(app._expanded), expanded)
            self.assertEqual(set(app._collapsed), collapsed)
            self.assertTrue(app._row_nodes[plan_key].is_expanded)
            self.assertFalse(app._row_nodes[milestone_key].is_expanded)

    async def test_a_closed_plan_stays_closed_and_hides_a_new_milestone(self) -> None:
        app = create_app(self.store.path)
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            self.expand_all(app)
            await pilot.pause()
            plan_key = ("plan", self.plan.id)
            app.selected = plan_key
            app.tree_controller.fold_one()
            await pilot.pause()
            expanded = set(app._expanded)
            added = self.store.add_milestone(self.plan.id, "Later", actor="ana")
            app.refresh_all()
            await pilot.pause()
            self.assertEqual(set(app._expanded), expanded)
            plan_node = app._row_nodes[plan_key]
            self.assertFalse(plan_node.is_expanded)
            milestone_node = app._row_nodes[("milestone", added.id)]
            self.assertFalse(milestone_node.is_expanded)
            self.assertLess(milestone_node._line, 0)

    async def test_a_new_milestone_under_an_open_plan_appears_collapsed(self) -> None:
        app = create_app(self.store.path)
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            self.expand_all(app)
            await pilot.pause()
            expanded = set(app._expanded)
            added = self.store.add_milestone(self.plan.id, "Later", actor="ana")
            app.refresh_all()
            await pilot.pause()
            self.assertEqual(set(app._expanded), expanded)
            self.assertTrue(app._row_nodes[("plan", self.plan.id)].is_expanded)
            milestone_node = app._row_nodes[("milestone", added.id)]
            self.assertFalse(milestone_node.is_expanded)
            self.assertTrue(app.tree_controller.is_visible(milestone_node))

    async def test_selecting_a_hidden_task_keeps_the_branch_closed(self) -> None:
        app = create_app(self.store.path)
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            self.expand_all(app)
            await pilot.pause()
            milestone_key = ("milestone", self.milestone.id)
            app.selected = milestone_key
            app.tree_controller.fold_one()
            await pilot.pause()
            app.select_row("task", self.task.id)
            await pilot.pause()
            self.assertEqual(app.selected, milestone_key)
            self.assertNotIn(milestone_key, app._expanded)
            self.assertFalse(app._row_nodes[milestone_key].is_expanded)
            tree = app.query_one("#tree", Tree)
            self.assertEqual(_node_key(tree.cursor_node), milestone_key)

    async def test_deleting_the_cursor_row_falls_back_to_a_visible_survivor(self) -> None:
        app = create_app(self.store.path)
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            self.expand_all(app)
            await pilot.pause()
            tree = app.query_one("#tree", Tree)
            tree.focus()
            tree.move_cursor(app._row_nodes[("task", self.task.id)])
            await pilot.pause()
            self.store.delete("task", self.task.id, actor="ana")
            app.refresh_all()
            await pilot.pause()
            self.assertNotIn(("task", self.task.id), app._row_nodes)
            cursor = tree.cursor_node
            self.assertIsNotNone(cursor)
            self.assertEqual(app.selected, ("milestone", self.milestone.id))
            self.assertEqual(_node_key(cursor), app.selected)
            self.assertTrue(app.tree_controller.is_visible(cursor))


class TestFilterExpansion(RefreshCase):
    async def test_a_filter_reveals_a_hit_and_restores_the_baseline(self) -> None:
        second = self.store.add_task(self.milestone.id, "Needle", actor="ana")
        app = create_app(self.store.path)
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            self.expand_all(app)
            await pilot.pause()
            milestone_key = ("milestone", self.milestone.id)
            app.selected = milestone_key
            app.tree_controller.fold_one()
            await pilot.pause()
            expanded = set(app._expanded)
            collapsed = set(app._collapsed)
            app.filter_text = "Needle"
            app.refresh_all()
            await pilot.pause()
            hit = app._row_nodes[("task", second.id)]
            self.assertTrue(app.tree_controller.is_visible(hit))
            self.assertEqual(set(app._expanded), expanded)
            self.assertEqual(set(app._collapsed), collapsed)
            app.filter_text = ""
            app.refresh_all()
            await pilot.pause()
            self.assertEqual(set(app._expanded), expanded)
            self.assertEqual(set(app._collapsed), collapsed)
            self.assertFalse(app._row_nodes[milestone_key].is_expanded)
            self.assertFalse(app.tree_controller.is_visible(app._row_nodes[("task", second.id)]))

    async def test_a_second_filter_keeps_the_first_baseline(self) -> None:
        second = self.store.add_task(self.milestone.id, "Needle", actor="ana")
        app = create_app(self.store.path)
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            self.expand_all(app)
            await pilot.pause()
            milestone_key = ("milestone", self.milestone.id)
            app.selected = milestone_key
            app.tree_controller.fold_one()
            await pilot.pause()
            expanded = set(app._expanded)
            collapsed = set(app._collapsed)
            for text in ("Needle", "Task"):
                app.filter_text = text
                app.refresh_all()
                await pilot.pause()
                self.assertEqual(set(app._expanded), expanded)
                self.assertEqual(set(app._collapsed), collapsed)
            app.filter_text = ""
            app.refresh_all()
            await pilot.pause()
            self.assertEqual(set(app._expanded), expanded)
            self.assertEqual(set(app._collapsed), collapsed)
            self.assertFalse(app._row_nodes[milestone_key].is_expanded)
            self.assertIn(("task", second.id), app._row_nodes)


class TestExpansionMatrix(RefreshCase):
    """Every structural write leaves each branch exactly as the reader left it."""

    def states(self, app: object, keys: list[tuple[str, int]]) -> dict[tuple[str, int], bool]:
        return {key: bool(app._row_nodes[key].is_expanded) for key in keys}  # type: ignore[attr-defined]

    def identities(self, app: object, keys: list[tuple[str, int]]) -> dict[tuple[str, int], int]:
        return {key: id(app._row_nodes[key]) for key in keys}  # type: ignore[attr-defined]

    def assert_unchanged(
        self,
        app: object,
        keys: list[tuple[str, int]],
        states: dict[tuple[str, int], bool],
        identities: dict[tuple[str, int], int],
        expanded: set[tuple[str, int]],
        collapsed: set[tuple[str, int]],
    ) -> None:
        self.assertEqual(self.states(app, keys), states)
        self.assertEqual(self.identities(app, keys), identities)
        self.assertEqual(set(app._expanded), expanded)  # type: ignore[attr-defined]
        self.assertEqual(set(app._collapsed), collapsed)  # type: ignore[attr-defined]

    async def test_add_edit_delete_and_rollup_keep_branch_state(self) -> None:
        app = create_app(self.store.path)
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            self.expand_all(app)
            await pilot.pause()
            plan_key = ("plan", self.plan.id)
            milestone_key = ("milestone", self.milestone.id)
            keys = [plan_key, milestone_key]
            states = self.states(app, keys)
            identities = self.identities(app, keys)
            expanded = set(app._expanded)
            collapsed = set(app._collapsed)
            added = self.store.add_task(self.milestone.id, "Second", actor="ana")
            app.refresh_all()
            await pilot.pause()
            self.assert_unchanged(app, keys, states, identities, expanded, collapsed)
            self.store.update_task(added.id, title="Renamed", actor="ana")
            app.refresh_all()
            await pilot.pause()
            self.assert_unchanged(app, keys, states, identities, expanded, collapsed)
            services.set_status(self.store, "task", self.task.id, Status.DONE, actor="ana")
            app.refresh_all()
            await pilot.pause()
            self.store.delete("task", added.id, actor="ana")
            app.refresh_all()
            await pilot.pause()
            self.assert_unchanged(app, keys, states, identities, expanded, collapsed)

    async def test_a_reorder_keeps_the_open_branch_open(self) -> None:
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
            self.expand_all(app)
            await pilot.pause()
            plan_key = ("plan", self.plan.id)
            milestone_key = ("milestone", self.milestone.id)
            expanded = set(app._expanded)
            collapsed = set(app._collapsed)
            self.store.log("ana", "plan", "edit", f"plan #{plans[1].id} touched", now=base + 7)
            app.refresh_all()
            await pilot.pause()
            self.assertEqual(set(app._expanded), expanded)
            self.assertEqual(set(app._collapsed), collapsed)
            self.assertTrue(app._row_nodes[plan_key].is_expanded)
            self.assertTrue(app._row_nodes[milestone_key].is_expanded)
            self.assertTrue(app.tree_controller.is_visible(app._row_nodes[("task", self.task.id)]))

    async def test_a_plan_rollup_moves_panels_and_keeps_state_and_cursor(self) -> None:
        app = create_app(self.store.path)
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            self.expand_all(app)
            await pilot.pause()
            tree = app.query_one("#tree", Tree)
            tree.focus()
            tree.move_cursor(app._row_nodes[("task", self.task.id)])
            await pilot.pause()
            plan_key = ("plan", self.plan.id)
            milestone_key = ("milestone", self.milestone.id)
            task_key = ("task", self.task.id)
            expanded = set(app._expanded)
            collapsed = set(app._collapsed)
            services.set_status(self.store, "task", self.task.id, Status.DONE, actor="ana")
            app.refresh_all()
            await pilot.pause()
            self.assertEqual(set(app._expanded), expanded)
            self.assertEqual(set(app._collapsed), collapsed)
            plan_node = app._row_nodes[plan_key]
            self.assertIs(plan_node.tree, app.query_one("#tree-finished", Tree))
            self.assertTrue(plan_node.is_expanded)
            self.assertTrue(app._row_nodes[milestone_key].is_expanded)
            self.assertTrue(app.tree_controller.is_visible(app._row_nodes[task_key]))
            self.assertEqual(app.selected, task_key)
            self.assertEqual(_node_key(app.query_one("#tree-finished", Tree).cursor_node), task_key)
            services.set_status(self.store, "task", self.task.id, Status.TODO, actor="ana")
            app.refresh_all()
            await pilot.pause()
            self.assertIs(app._row_nodes[plan_key].tree, app.query_one("#tree", Tree))
            self.assertTrue(app._row_nodes[plan_key].is_expanded)
            self.assertTrue(app.tree_controller.is_visible(app._row_nodes[task_key]))


class TestViewPreservation(RefreshCase):
    def busy_tree(self) -> None:
        """Make the plan list long enough to scroll and keep the fixture on top."""
        for index in range(20):
            self.store.add_plan(f"Extra {index}")
        self.store.update_plan(self.plan.id, goal="most recent", actor="ana")

    async def settled_tree(self, pilot: Any) -> Tree:
        """The plan tree once the first layout stops resizing it.

        On Windows a bare pause can return before the panes finish their first
        layout, and the tree then shrinks under a cursor the test already placed.
        """
        tree = pilot.app.query_one("#tree", Tree)
        height = -1
        for _ in range(50):
            await pilot.pause(0.02)
            if tree.scrollable_content_region.height == height:
                return tree
            height = tree.scrollable_content_region.height
        self.fail("the tree layout never settled")

    async def test_cursor_and_scroll_survive_a_structural_update(self) -> None:
        self.busy_tree()
        app = create_app(self.store.path)
        async with app.run_test(size=(120, 18)) as pilot:
            tree = await self.settled_tree(pilot)
            tree.move_cursor(list(app._row_nodes.values())[4])
            tree.scroll_to(y=3, animate=False)
            await pilot.pause()
            cursor_line = tree.cursor_line
            scroll = tree.scroll_offset
            focused = tree.has_focus
            self.store.update_task(self.task.id, title="Renamed", actor="ana")
            app.refresh_all()
            await pilot.pause()
            self.assertEqual(tree.cursor_line, cursor_line)
            self.assertEqual(tree.scroll_offset, scroll)
            self.assertEqual(tree.has_focus, focused)

    async def test_cursor_and_scroll_survive_a_heartbeat(self) -> None:
        self.busy_tree()
        session_id = self.open_session()
        app = create_app(self.store.path)
        async with app.run_test(size=(120, 18)) as pilot:
            tree = await self.settled_tree(pilot)
            harness = self.harness(app, session_id)
            tree.move_cursor(list(app._row_nodes.values())[4])
            tree.scroll_to(y=3, animate=False)
            await pilot.pause()
            cursor_line = tree.cursor_line
            scroll = tree.scroll_offset
            harness.heartbeat("waiting")
            await pilot.pause()
            self.assertEqual(tree.cursor_line, cursor_line)
            self.assertEqual(tree.scroll_offset, scroll)

    async def test_an_unselected_change_keeps_the_preview_document(self) -> None:
        other = self.store.add_plan("Other")
        self.store.update_plan(self.plan.id, goal="most recent", actor="ana")
        app = create_app(self.store.path)
        async with app.run_test(size=(120, 24)) as pilot:
            await pilot.pause()
            app.selected = ("plan", other.id)
            app.update_preview(force=True)
            await pilot.pause()
            panel = app.query_one("#preview", PreviewPanel)
            calls: list[object] = []
            original = panel.show

            def spy(document: object, strip: str = "") -> None:
                calls.append(document)
                original(document, strip)  # type: ignore[arg-type]

            panel.show = spy  # type: ignore[method-assign]
            self.store.update_task(self.task.id, title="Unrelated", actor="ana")
            app.refresh_all()
            await pilot.pause()
            self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
