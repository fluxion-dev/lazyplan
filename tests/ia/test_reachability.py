"""Every action reaches its destination within three tree interactions."""

from __future__ import annotations

import json
import os
import tempfile
import unittest

from lazyplan.presentation.shared import registry
from lazyplan.store import Store

try:
    from lazyplan.presentation import tui as tui_mod
except ImportError:  # pragma: no cover - stdlib-only interpreter
    tui_mod = None  # type: ignore[assignment]

from tests.support.pilot import settle, walk_route


class TestReachability(unittest.TestCase):
    def test_every_action_is_within_three_steps(self) -> None:
        report = registry.reachability_report()
        self.assertEqual(report["over_budget"], [])
        for row in report["actions"]:
            with self.subTest(action=row["id"]):
                self.assertLessEqual(row["depth"], 3)

    def test_report_is_machine_readable(self) -> None:
        report = registry.reachability_report()
        decoded = json.loads(json.dumps(report, sort_keys=True))
        self.assertEqual(decoded["max_depth"], 3)
        self.assertEqual(set(decoded["entities"]), set(registry.ENTITIES))
        self.assertGreater(len(decoded["actions"]), 0)
        self.assertEqual(decoded["over_budget"], [])

    def test_entity_depth_comes_from_its_actions(self) -> None:
        report = registry.reachability_report()
        plan_depths = [row["depth"] for row in report["actions"] if row["id"].startswith("plan.")]
        self.assertEqual(report["entities"]["plan"], min(plan_depths))

    def test_four_step_route_fails_and_names_the_route(self) -> None:
        deep = registry.Action(
            "plan.deep",
            "Deep route",
            route=("tree", "detail", "trust", "deeper", "deepest"),
        )
        errors = registry.check_reachability((deep,))
        self.assertEqual(len(errors), 1)
        self.assertIn("plan.deep", errors[0])
        self.assertIn("4 steps", errors[0])
        self.assertIn("deeper", errors[0])


@unittest.skipUnless(tui_mod is not None and tui_mod._TEXTUAL_OK, "textual not installed")
class TestRouteWalk(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "reach.db")
        store = Store(self.db)
        plan = store.add_plan("Reach", "What", goal="Why")
        milestone = store.add_milestone(plan.id, "M", "As a user.")
        self.task = store.add_task(milestone.id, "T", "Commit: one.")

    async def asyncTearDown(self) -> None:
        self.tmp.cleanup()

    async def test_walk_route_records_detail_source_and_back(self) -> None:
        app = tui_mod.create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            await settle(pilot)
            app.selected = ("task", self.task.id)
            seen = await walk_route(pilot, ("enter", "g", "escape", "escape"))
            self.assertEqual(seen, ["tree", "detail", "source", "detail", "tree"])
