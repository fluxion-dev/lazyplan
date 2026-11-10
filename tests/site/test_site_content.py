"""The feature catalog, story copy, and capture plan agree with the narrative."""

from __future__ import annotations

import json
import re
import unittest

from tests.support.paths import ROOT
from tests.support.site import has_built_site, page_html

FEATURES = ROOT / "site/src/data/features.json"
SCREENS = ROOT / "site/src/data/screens.ts"
COPY = ROOT / "site/src/data/copy.ts"
HERO = ROOT / "site/src/components/site/hero.tsx"

LEAD_IDS = ["shared-plan", "agent-loop", "proof"]
SUPPORT_IDS = {
    "control-room",
    "trust-hubs",
    "claims",
    "sessions",
    "workbench",
    "source-trail",
    "timeline",
    "keyboard",
    "themes",
    "local-first",
    "auditability",
    "bulk-search",
}
ICONS = {
    "activity",
    "bot",
    "database",
    "git-branch",
    "keyboard",
    "list-checks",
    "lock",
    "messages-square",
    "monitor",
    "network",
    "palette",
    "route",
    "search",
    "shield-check",
    "timer",
}
GROUPS = {"plan", "agents", "proof", "product"}
CAPTURE_FILES = [
    "lpui-control-room",
    "lpui-detail",
    "lpui-coordination",
    "lpui-workbench",
    "lpui-trace",
    "lpui-source-trail",
    "lpui-git-pane",
    "lpui-timeline",
]


class TestFeatureCatalog(unittest.TestCase):
    def setUp(self):
        data = json.loads(FEATURES.read_text(encoding="utf-8"))
        self.lead = data["lead"]
        self.support = data["support"]
        self.all = [*self.lead, *self.support]

    def test_lead_trio_is_the_story(self):
        self.assertEqual([feature["id"] for feature in self.lead], LEAD_IDS)

    def test_support_covers_the_major_surfaces(self):
        ids = {feature["id"] for feature in self.support}
        self.assertGreaterEqual(len(ids), 12)
        self.assertEqual(ids, SUPPORT_IDS)

    def test_every_feature_is_complete(self):
        for feature in self.all:
            with self.subTest(feature=feature["id"]):
                self.assertTrue(feature["title"].strip())
                self.assertTrue(feature["description"].strip())
                self.assertIn(feature["icon"], ICONS)
                self.assertIn(feature["group"], GROUPS)

    def test_ids_are_unique(self):
        ids = [feature["id"] for feature in self.all]
        self.assertEqual(len(ids), len(set(ids)))


class TestCaptureStory(unittest.TestCase):
    def setUp(self):
        self.source = SCREENS.read_text(encoding="utf-8")

    def _story_block(self) -> str:
        match = re.search(
            r"export const STORY_SCREENS: readonly Screen\[\] = \[(.*?)\n\]",
            self.source,
            re.S,
        )
        assert match is not None
        return match.group(1)

    def test_eight_supporting_captures(self):
        block = self._story_block()
        self.assertEqual(re.findall(r'file: "([^"]+)"', block), CAPTURE_FILES)
        self.assertEqual(len(re.findall(r'name: "', block)), 8)
        self.assertEqual(len(re.findall(r'alt: "', block)), 8)
        self.assertEqual(len(re.findall(r'caption: "', block)), 8)

    def test_hero_composite_is_wide(self):
        match = re.search(r"export const HERO_COMPOSITE: Screen = \{(.*?)\n\}", self.source, re.S)
        assert match is not None
        block = match.group(1)
        self.assertIn('file: "lpui-hero"', block)
        self.assertIn("width: 2400", block)
        self.assertIn("height: 1200", block)
        self.assertIn('alt: "', block)


class TestStoryCopy(unittest.TestCase):
    def test_source_keeps_the_hero_and_adds_proof_copy(self):
        source = COPY.read_text(encoding="utf-8")
        hero = HERO.read_text(encoding="utf-8")
        self.assertIn("Your master plan(s), laid bare.", hero)
        self.assertIn("Agent compatible long context planning and control", hero)
        self.assertIn("The work leaves a trail.", source)

    @unittest.skipUnless(has_built_site(), "site not built")
    def test_section_copy_is_rendered(self):
        page = page_html()
        for phrase in (
            "One plan. Two workers. No lost context.",
            "Every row is a workspace.",
            "The app, in use.",
            "Start with a plan. Finish with proof.",
            "Get the plan into your terminal.",
            "Bring your plan into focus.",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, page)


if __name__ == "__main__":
    unittest.main()
