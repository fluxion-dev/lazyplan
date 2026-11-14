"""Session brief: active plans and their tasks come from one shared selection."""

from __future__ import annotations

import ast
import tempfile
import unittest
from pathlib import Path

from lazyplan.core.entities import Status
from lazyplan.services import active
from lazyplan.store import Store

SERVICES = Path(__file__).resolve().parents[2] / "src" / "lazyplan" / "services"


class ActiveSelectionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(Path(self.tmp.name) / "active.db")

    def make_plan(self, name: str, status: Status = Status.TODO) -> tuple[int, int]:
        """Add a plan with one milestone and two tasks; return both ids."""
        plan = self.store.add_plan(name, actor="fixture")
        milestone = self.store.add_milestone(plan.id, f"{name} M", actor="fixture")
        self.store.add_task(milestone.id, f"{name} one", actor="fixture")
        self.store.add_task(milestone.id, f"{name} two", actor="fixture")
        if status != Status.TODO:
            self.store.set_status_raw("plan", plan.id, status)
        return plan.id, milestone.id

    def test_requested_plan_wins_over_the_live_list(self) -> None:
        first, _ = self.make_plan("first")
        second, _ = self.make_plan("second", Status.DOING)
        self.assertEqual([plan.id for plan in active.active_plans(self.store, second)], [second])
        self.assertEqual(active.selected_plan(self.store, first), self._plan(first))

    def test_archived_or_missing_plan_selects_nothing(self) -> None:
        plan_id, _ = self.make_plan("gone")
        self.store.set_plan_archived(plan_id, 1_000.0, actor="fixture")
        self.assertEqual(active.plan_list(self.store, plan_id), [])
        self.assertIsNone(active.selected_plan(self.store, plan_id))
        self.assertIsNone(active.selected_plan(self.store, 9999))

    def test_doing_plans_beat_todo_plans(self) -> None:
        self.make_plan("todo only")
        doing, _ = self.make_plan("doing", Status.DOING)
        self.assertEqual([plan.id for plan in active.next_plans(self.store)], [doing])

    def test_todo_fallback_carries_one_plan(self) -> None:
        self.make_plan("older")
        newest, _ = self.make_plan("newest")
        self.assertEqual([plan.id for plan in active.next_plans(self.store)], [newest])

    def test_doing_limit_is_respected(self) -> None:
        ids = [self.make_plan(f"p{index}", Status.DOING)[0] for index in range(4)]
        self.assertEqual(
            [plan.id for plan in active.active_plans(self.store, limit=2)],
            [ids[3], ids[2]],
        )
        self.assertEqual(len(active.active_plans(self.store)), 3)

    def test_no_plan_selects_nothing(self) -> None:
        self.assertIsNone(active.selected_plan(self.store))
        self.assertEqual(active.active_plans(self.store), [])

    def test_plan_list_without_an_id_is_every_live_plan(self) -> None:
        first, _ = self.make_plan("first")
        second, _ = self.make_plan("second")
        self.assertEqual([plan.id for plan in active.plan_list(self.store)], [second, first])

    def test_tasks_for_walks_milestones_in_order(self) -> None:
        plan_id, milestone_id = self.make_plan("walk")
        second = self.store.add_milestone(plan_id, "second M", actor="fixture")
        self.store.add_task(second.id, "third", actor="fixture")
        titles = [task.title for task in active.tasks_for(self.store, self._plan(plan_id))]
        self.assertEqual(titles, ["walk one", "walk two", "third"])

    def test_task_index_shares_maps_across_plans(self) -> None:
        first, first_m = self.make_plan("first")
        second, _ = self.make_plan("second")
        task_plan, task_by_id, by_plan = active.task_index(self.store, [first, second])
        self.assertEqual(len(task_plan), 4)
        self.assertEqual(len(task_by_id), 4)
        self.assertEqual(set(by_plan), {first, second})
        self.assertEqual([task.milestone_id for task in by_plan[first]], [first_m, first_m])

    def test_all_tasks_covers_live_plans_only(self) -> None:
        live, _ = self.make_plan("live")
        gone, _ = self.make_plan("gone")
        self.store.set_plan_archived(gone, 1_000.0, actor="fixture")
        self.assertEqual(
            [task.title for task in active.all_tasks(self.store)], ["live one", "live two"]
        )

    def test_module_imports_no_presentation(self) -> None:
        tree = ast.parse((SERVICES / "active.py").read_text(encoding="utf-8"))
        roots = {
            node.module.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }
        roots |= {
            alias.name.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        self.assertNotIn("presentation", roots)
        self.assertNotIn("store", roots)

    def _plan(self, plan_id: int):
        plan = self.store.get_plan(plan_id)
        assert plan is not None
        return plan


if __name__ == "__main__":
    unittest.main()
