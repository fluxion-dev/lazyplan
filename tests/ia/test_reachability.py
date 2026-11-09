"""Every action reaches its destination within three tree interactions."""

from __future__ import annotations

import json
import unittest

from lazyplan.presentation.shared import registry
from tests.support.paths import ROOT

REPORT_JSON = ROOT / "docs/information-architecture/reachability.json"
REPORT_MD = ROOT / "docs/information-architecture/reachability.md"


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
            route=("tree", "hub", "trust", "deeper", "deepest"),
        )
        errors = registry.check_reachability((deep,))
        self.assertEqual(len(errors), 1)
        self.assertIn("plan.deep", errors[0])
        self.assertIn("4 steps", errors[0])
        self.assertIn("deeper", errors[0])

    def test_committed_report_matches_the_registry(self) -> None:
        committed = json.loads(REPORT_JSON.read_text(encoding="utf-8"))
        self.assertEqual(committed, registry.reachability_report())

    def test_committed_markdown_names_every_action(self) -> None:
        text = REPORT_MD.read_text(encoding="utf-8")
        for action in registry.ACTIONS:
            with self.subTest(action=action.id):
                self.assertIn(f"`{action.id}`", text)

    def test_committed_report_has_no_over_budget_rows(self) -> None:
        committed = json.loads(REPORT_JSON.read_text(encoding="utf-8"))
        self.assertEqual(committed["over_budget"], [])
        self.assertTrue(all(row["depth"] <= 3 for row in committed["actions"]))
