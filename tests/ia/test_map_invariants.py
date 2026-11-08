"""The IA map covers every entity, journey, and finding disposition."""

from __future__ import annotations

import re
import unittest

from lazyplan.presentation.shared.registry import ACTIONS, ENTITIES
from tests.support.paths import ROOT

SPEC = (ROOT / "docs/information-architecture/spec.md").read_text(encoding="utf-8")
FINDINGS = (ROOT / "docs/information-architecture/findings.md").read_text(encoding="utf-8")


class TestMapInvariants(unittest.TestCase):
    def test_every_entity_appears_once_in_the_model(self):
        for entity in ENTITIES:
            with self.subTest(entity=entity):
                self.assertIn(f"| `{entity}` |", SPEC)

    def test_every_journey_is_named(self):
        for journey in (
            "Capture",
            "Organize",
            "Execute",
            "Prove",
            "Ship",
            "Inspect",
            "Coordinate",
            "Administer",
        ):
            with self.subTest(journey=journey):
                self.assertIn(f"| {journey} |", SPEC)

    def test_every_action_has_a_route_and_surface(self):
        for action in ACTIONS:
            with self.subTest(action=action.id):
                self.assertTrue(action.route)
                self.assertTrue(action.surfaces)

    def test_every_finding_has_a_target(self):
        rows = re.findall(r"^\| (IA-\d+) \|", FINDINGS, re.M)
        self.assertGreaterEqual(len(rows), 5)
        for finding in rows:
            line = next(line for line in FINDINGS.splitlines() if line.startswith(f"| {finding} |"))
            self.assertRegex(line, r"\| (High|Medium|Low|Closed) \|")
            self.assertRegex(line, r"\| (M45\d(–M45\d)?|Closed) \|")

    def test_setup_steps_and_hook_events_are_mapped(self):
        from lazyplan.infrastructure.hook_hosts import EVENTS
        from lazyplan.presentation.shared.registry import HOOK_EVENTS, SETUP_STEPS

        ui_source = (ROOT / "src/lazyplan/presentation/setup/ui.py").read_text(encoding="utf-8")
        for step in SETUP_STEPS:
            with self.subTest(step=step):
                self.assertIn(f"def {step}(", ui_source)
        found = {event for events in EVENTS.values() for event in events}
        self.assertEqual(set(HOOK_EVENTS), found)

    def test_spec_links_resolve(self):
        for target in re.findall(r"\]\(([^)]+)\)", SPEC):
            self.assertTrue((ROOT / "docs/information-architecture" / target).is_file(), target)
