"""Pure approval snapshot and drift rules."""

from __future__ import annotations

import copy
import unittest
from typing import Any

from lazyplan.core.entities import Criterion, Milestone, Plan, Status, Task
from lazyplan.core.policies.revisions import (
    SNAPSHOT_SCHEMA,
    build_snapshot,
    canonical,
    diff_snapshots,
    digest,
    summarize,
)


def sample() -> tuple[
    Plan,
    list[Milestone],
    dict[int, list[Task]],
    dict[tuple[str, int], list[Criterion]],
    dict[tuple[str, int], str],
]:
    """One small plan tree with stable keys on some rows."""
    plan = Plan(id=1, name="Plan", description="what", goal="why")
    milestones = [
        Milestone(id=10, plan_id=1, title="M1", description="d1"),
        Milestone(id=20, plan_id=1, title="M2", description="d2"),
    ]
    tasks = {
        10: [
            Task(id=100, milestone_id=10, title="T1", description="t1 desc"),
            Task(id=101, milestone_id=10, title="T2", description="t2 desc"),
        ],
        20: [Task(id=200, milestone_id=20, title="T3", description="t3 desc")],
    }
    criteria = {
        ("plan", 1): [Criterion(id=1000, parent_kind="plan", parent_id=1, text="p1")],
        ("milestone", 10): [Criterion(id=1100, parent_kind="milestone", parent_id=10, text="m1")],
        ("milestone", 20): [Criterion(id=2100, parent_kind="milestone", parent_id=20, text="m2")],
        ("task", 100): [
            Criterion(id=1200, parent_kind="task", parent_id=100, text="t1a"),
            Criterion(id=1201, parent_kind="task", parent_id=100, text="t1b"),
        ],
        ("task", 101): [Criterion(id=1300, parent_kind="task", parent_id=101, text="t2a")],
        ("task", 200): [Criterion(id=2200, parent_kind="task", parent_id=200, text="t3a")],
    }
    keys = {
        ("plan", 1): "plan-key",
        ("milestone", 10): "m1",
        ("task", 100): "t1",
    }
    return plan, milestones, tasks, criteria, keys


def snapshot() -> dict[str, Any]:
    plan, milestones, tasks, criteria, keys = sample()
    return build_snapshot(plan, milestones, tasks, criteria, keys)


class TestSnapshot(unittest.TestCase):
    def test_shape_and_order(self) -> None:
        snap = snapshot()
        self.assertEqual(snap["schema"], SNAPSHOT_SCHEMA)
        self.assertEqual(snap["plan"]["title"], "Plan")
        self.assertEqual([item["id"] for item in snap["milestones"]], [10, 20])
        self.assertEqual([item["id"] for item in snap["milestones"][0]["tasks"]], [100, 101])
        self.assertEqual(
            [item["id"] for item in snap["milestones"][0]["tasks"][0]["criteria"]],
            [1200, 1201],
        )

    def test_scope_only(self) -> None:
        plan, milestones, tasks, criteria, keys = sample()
        plan.status = Status.DONE
        milestones[0].status = Status.DONE
        tasks[10][0].status = Status.DONE
        criteria[("task", 100)][0].done = True
        changed = build_snapshot(plan, milestones, tasks, criteria, keys)
        self.assertEqual(digest(changed), digest(snapshot()))

    def test_digest_is_canonical(self) -> None:
        snap = snapshot()
        reordered = {"milestones": snap["milestones"], "plan": snap["plan"], "schema": 1}
        self.assertEqual(canonical(snap), canonical(reordered))
        self.assertEqual(digest(snap), digest(reordered))

    def test_identity_prefers_stable_key(self) -> None:
        snap = snapshot()
        self.assertEqual(snap["plan"]["key"], "plan-key")
        self.assertEqual(snap["milestones"][0]["key"], "m1")
        self.assertEqual(snap["milestones"][0]["tasks"][0]["key"], "t1")
        self.assertEqual(snap["milestones"][0]["tasks"][1]["key"], "")


class TestDiff(unittest.TestCase):
    def test_unchanged_is_empty(self) -> None:
        self.assertEqual(diff_snapshots(snapshot(), snapshot()), ())

    def test_plan_field_change(self) -> None:
        before = snapshot()
        after = copy.deepcopy(before)
        after["plan"]["what"] = "new what"
        changes = diff_snapshots(before, after)
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].kind, "plan")
        self.assertEqual(changes[0].action, "change")
        self.assertEqual(changes[0].field, "what")
        self.assertEqual(changes[0].before, "what")
        self.assertEqual(changes[0].after, "new what")

    def test_added_milestone_covers_its_children(self) -> None:
        before = snapshot()
        after = copy.deepcopy(before)
        after["milestones"].append(
            {
                "id": 30,
                "key": "m3",
                "title": "M3",
                "desc": "d3",
                "criteria": [{"id": 3000, "text": "m3a"}],
                "tasks": [
                    {
                        "id": 300,
                        "key": "t4",
                        "title": "T4",
                        "desc": "t4 desc",
                        "criteria": [{"id": 3100, "text": "t4a"}],
                    }
                ],
            }
        )
        changes = diff_snapshots(before, after)
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].kind, "milestone")
        self.assertEqual(changes[0].action, "add")

    def test_removed_milestone_covers_its_children(self) -> None:
        before = snapshot()
        after = copy.deepcopy(before)
        after["milestones"] = [item for item in after["milestones"] if item["id"] != 20]
        changes = diff_snapshots(before, after)
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].kind, "milestone")
        self.assertEqual(changes[0].action, "remove")
        self.assertEqual(changes[0].obj_id, 20)

    def test_task_and_criterion_changes(self) -> None:
        before = snapshot()
        after = copy.deepcopy(before)
        tasks = after["milestones"][0]["tasks"]
        tasks[0]["title"] = "T1 renamed"
        tasks[0]["criteria"][0]["text"] = "t1a changed"
        tasks.append(
            {
                "id": 102,
                "key": "t2b",
                "title": "T2b",
                "desc": "new task",
                "criteria": [{"id": 1400, "text": "t2b proof"}],
            }
        )
        changes = diff_snapshots(before, after)
        actions = [(change.kind, change.action, change.obj_id) for change in changes]
        self.assertEqual(
            actions,
            [
                ("task", "change", 100),
                ("task", "add", 102),
                ("criterion", "change", 1200),
            ],
        )

    def test_task_move(self) -> None:
        before = snapshot()
        after = copy.deepcopy(before)
        moved = after["milestones"][0]["tasks"].pop(0)
        after["milestones"][1]["tasks"].append(moved)
        changes = diff_snapshots(before, after)
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].kind, "task")
        self.assertEqual(changes[0].action, "move")
        self.assertEqual(changes[0].before, "m1")
        self.assertEqual(changes[0].after, "milestone:20")

    def test_removed_task_hides_its_criteria(self) -> None:
        before = snapshot()
        after = copy.deepcopy(before)
        after["milestones"][0]["tasks"] = [
            item for item in after["milestones"][0]["tasks"] if item["id"] != 100
        ]
        changes = diff_snapshots(before, after)
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].kind, "task")
        self.assertEqual(changes[0].action, "remove")

    def test_status_and_ticks_are_ignored(self) -> None:
        before = snapshot()
        after = copy.deepcopy(before)
        after["plan"]["status"] = "done"
        after["milestones"][0]["tasks"][0]["status"] = "done"
        after["milestones"][0]["tasks"][0]["criteria"][0]["done"] = True
        self.assertEqual(diff_snapshots(before, after), ())

    def test_summary_counts_actions(self) -> None:
        before = snapshot()
        after = copy.deepcopy(before)
        after["plan"]["title"] = "Renamed"
        after["milestones"][0]["tasks"][0]["title"] = "T1 renamed"
        after["milestones"].append(
            {
                "id": 30,
                "key": "",
                "title": "M3",
                "desc": "",
                "criteria": [],
                "tasks": [],
            }
        )
        changes = diff_snapshots(before, after)
        self.assertEqual(
            summarize(changes), {"add": 1, "remove": 0, "change": 2, "move": 0, "total": 3}
        )

    def test_empty_plan(self) -> None:
        plan = Plan(id=1, name="Empty")
        before = build_snapshot(plan, [], {}, {}, {})
        after = build_snapshot(
            plan,
            [Milestone(id=10, plan_id=1, title="M1")],
            {},
            {},
            {},
        )
        changes = diff_snapshots(before, after)
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].kind, "milestone")
        self.assertEqual(changes[0].action, "add")


if __name__ == "__main__":
    unittest.main()
