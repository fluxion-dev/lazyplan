"""Tree rows keep their stat slots in the same place across states and widths."""

from __future__ import annotations

import os
import tempfile
import unittest
from typing import Any

from lazyplan import services
from lazyplan.design import RowStats, render_stats, stats_layout
from lazyplan.store import Store

try:
    from rich.text import Text
    from textual.widgets import Tree

    from lazyplan import tui as tui_mod
except ImportError:  # stdlib-only interpreter
    Text = None  # type: ignore[assignment,misc]
    Tree = None  # type: ignore[assignment,misc]
    tui_mod = None  # type: ignore[assignment]


@unittest.skipUnless(
    tui_mod is not None and tui_mod._TEXTUAL_OK and Text is not None,
    "textual not installed",
)
class TreeStatsTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "t.db")
        store = Store(self.db)
        self.plan_a = store.add_plan("Plan A")
        self.milestone_a = store.add_milestone(self.plan_a.id, "Milestone A")
        self.task_a = store.add_task(self.milestone_a.id, "Task A")
        self.plan_b = store.add_plan("Plan B")
        self.milestone_b = store.add_milestone(self.plan_b.id, "Milestone B")
        self.task_b = store.add_task(self.milestone_b.id, "Task B")
        self.task_c = store.add_task(self.milestone_b.id, "Task C")
        store.link_commit("task", self.task_b.id, "a" * 40, subject="work")
        store.link_forge("task", self.task_b.id, 7, state="open", checks="pass")
        store.claim_task(self.task_b.id, "alice")
        services.block_task(store, self.task_c.id, "waiting", actor="qa")
        self.store = Store(self.db)

    async def asyncTearDown(self) -> None:
        self.tmp.cleanup()

    @staticmethod
    def _plain(app: Any, key: tuple[str, int]) -> str:
        return Text.from_markup(app._row_labels[key]).plain

    async def test_stats_slots_are_stable_across_states_and_widths(self) -> None:
        expected = {
            "plan": {
                self.plan_a.id: RowStats(kind="plan", progress=(0, 1)),
                self.plan_b.id: RowStats(kind="plan", progress=(0, 2), commits=1, pulls=1),
            },
            "milestone": {
                self.milestone_a.id: RowStats(kind="milestone", progress=(0, 1)),
                self.milestone_b.id: RowStats(
                    kind="milestone", progress=(0, 2), commits=1, pulls=1
                ),
            },
            "task": {
                self.task_a.id: RowStats(kind="task"),
                self.task_b.id: RowStats(
                    kind="task",
                    commits=1,
                    pr_state="open",
                    pr_checks="pass",
                    claim_actor="alice",
                ),
                self.task_c.id: RowStats(kind="task", blocked=True),
            },
        }
        for width in (100, 120, 160):
            with self.subTest(width=width):
                app = tui_mod.create_app(self.db)
                app.marked.add(("plan", self.plan_a.id))
                app.marked.add(("task", self.task_a.id))
                async with app.run_test(size=(width, 40)) as pilot:
                    await pilot.pause()
                    await pilot.pause()
                    tree = app.query_one("#tree", Tree)
                    row_widths = {
                        "plan": app.tree_controller.row_width(tree, 3),
                        "milestone": app.tree_controller.row_width(tree, 7),
                        "task": app.tree_controller.row_width(tree, 11),
                    }
                    labels = {
                        "plan": {oid: self._plain(app, ("plan", oid)) for oid in expected["plan"]},
                        "milestone": {
                            oid: self._plain(app, ("milestone", oid))
                            for oid in expected["milestone"]
                        },
                        "task": {oid: self._plain(app, ("task", oid)) for oid in expected["task"]},
                    }
                    layouts: dict[str, tuple[tuple[str, bool], ...]] = {}
                    for kind, row_width in row_widths.items():
                        prefix = f"○ {kind[0].upper()}1 "
                        layout = stats_layout(kind, row_width, len(prefix))
                        layouts[kind] = layout
                        for oid, stats in expected[kind].items():
                            with self.subTest(width=width, kind=kind, id=oid):
                                block = render_stats(stats, layout)[1]
                                plain = labels[kind][oid]
                                self.assertEqual(len(plain), row_width)
                                self.assertEqual(plain[-len(block) :], block)

                    plan_b = labels["plan"][self.plan_b.id]
                    task_b = labels["task"][self.task_b.id]
                    task_c = labels["task"][self.task_c.id]
                    plan_keys = {key for key, _compact in layouts["plan"]}
                    task_slots = dict(layouts["task"])
                    if "commits" in plan_keys:
                        self.assertIn("1c", plan_b)
                    else:
                        self.assertNotIn("1c", plan_b)
                    if "claim" in task_slots:
                        self.assertIn("@alice", task_b)
                    else:
                        self.assertNotIn("@alice", task_b)
                    blocked_compact = task_slots.get("blocked")
                    if blocked_compact is None:
                        self.assertNotIn("⚑", task_c)
                    elif blocked_compact:
                        self.assertIn("⚑", task_c)
                        self.assertNotIn("⚑ blocked", task_c)
                    else:
                        self.assertIn("⚑ blocked", task_c)

                    for key in (("plan", self.plan_a.id), ("task", self.task_a.id)):
                        marked = str(app._row_nodes[key].label)
                        self.assertEqual(len(marked), row_widths[key[0]])
                        self.assertIn("✓", marked)


if __name__ == "__main__":
    unittest.main()
