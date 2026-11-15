"""Lane vocabulary: defaults, normalization, and strict validation."""

import unittest

from lazyplan.core.entities import Milestone, Plan, Task
from lazyplan.core.policies.lanes import (
    AGENT_ROLES,
    DEFAULT_AGENT_ROLE,
    DEFAULT_DISPATCH_MODE,
    DEFAULT_LANE_GROUP,
    DEFAULT_MAX_AGENTS,
    DISPATCH_MODES,
    check_agent_role,
    check_dispatch_mode,
    check_lane_group,
    check_max_agents,
    normalize_agent_role,
    normalize_dispatch_mode,
    normalize_lane_group,
    normalize_max_agents,
)


class TestLaneVocabulary(unittest.TestCase):
    def test_defaults_keep_legacy_rows_serial_and_roleless(self):
        plan = Plan(id=1, name="Legacy")
        milestone = Milestone(id=1, plan_id=1, title="Slice")
        task = Task(id=1, milestone_id=1, title="Work")
        self.assertEqual(plan.dispatch_mode, DEFAULT_DISPATCH_MODE)
        self.assertEqual(plan.max_agents, DEFAULT_MAX_AGENTS)
        self.assertEqual(milestone.lane_group, DEFAULT_LANE_GROUP)
        self.assertEqual(milestone.agent_role, DEFAULT_AGENT_ROLE)
        self.assertEqual(task.role, DEFAULT_AGENT_ROLE)

    def test_normalizers_take_known_values_and_fall_back(self):
        self.assertEqual(normalize_dispatch_mode(" PARALLEL "), "parallel")
        self.assertEqual(normalize_dispatch_mode("sometimes"), DEFAULT_DISPATCH_MODE)
        self.assertEqual(normalize_agent_role("QA"), "qa")
        self.assertEqual(normalize_agent_role("wizard"), DEFAULT_AGENT_ROLE)
        self.assertEqual(normalize_max_agents("3"), 3)
        self.assertEqual(normalize_max_agents(0), DEFAULT_MAX_AGENTS)
        self.assertEqual(normalize_max_agents("many"), DEFAULT_MAX_AGENTS)
        self.assertEqual(normalize_lane_group("2"), 2)
        self.assertEqual(normalize_lane_group(-1), DEFAULT_LANE_GROUP)

    def test_checks_reject_unknown_values(self):
        for value in ("", "sometimes", "SERIAL"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                check_dispatch_mode(value)
        for value in ("", "wizard", "QA"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                check_agent_role(value)
        for value in (0, -1, True, 1.5):
            with self.subTest(value=value), self.assertRaises(ValueError):
                check_max_agents(value)  # type: ignore[arg-type]
        for value in (0, -1, True, 1.5):
            with self.subTest(value=value), self.assertRaises(ValueError):
                check_lane_group(value)  # type: ignore[arg-type]

    def test_entities_validate_lane_fields(self):
        self.assertEqual(check_dispatch_mode(DISPATCH_MODES[0]), DISPATCH_MODES[0])
        self.assertEqual(check_agent_role(AGENT_ROLES[-1]), AGENT_ROLES[-1])
        with self.assertRaises(ValueError):
            Plan(id=1, name="P", dispatch_mode="sometimes")
        with self.assertRaises(ValueError):
            Plan(id=1, name="P", max_agents=0)
        with self.assertRaises(ValueError):
            Milestone(id=1, plan_id=1, title="M", lane_group=0)
        with self.assertRaises(ValueError):
            Milestone(id=1, plan_id=1, title="M", agent_role="wizard")
        with self.assertRaises(ValueError):
            Task(id=1, milestone_id=1, title="T", role="wizard")


if __name__ == "__main__":
    unittest.main()
