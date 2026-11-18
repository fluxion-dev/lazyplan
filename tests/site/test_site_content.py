"""The feature catalog, story copy, and capture plan agree with the narrative."""

from __future__ import annotations

import json
import re
import struct
import unittest

from tests.support.paths import ROOT
from tests.support.site import has_built_site, page_html

FEATURES = ROOT / "site/src/data/features.json"
SCREENS = ROOT / "site/src/data/screens.ts"
COPY = ROOT / "site/src/data/copy.ts"
SCREENS_DIR = ROOT / "site/public/screens"

LEAD_IDS = ["shared-plan", "dispatch", "proof"]
SUPPORT_IDS = {
    "setup",
    "models",
    "lanes",
    "worktrees",
    "claims",
    "handoffs",
    "control-room",
    "drafts",
    "trust-hubs",
    "evidence",
    "source-trail",
    "updates",
    "notifications",
    "local-first",
    "keyboard",
    "themes",
}
ICONS = {
    "activity",
    "database",
    "download",
    "git-branch",
    "keyboard",
    "layers",
    "list-checks",
    "lock",
    "messages-square",
    "network",
    "palette",
    "route",
    "shield-check",
    "sliders",
    "sparkles",
}
GROUPS = {"plan", "agents", "proof", "product"}
GALLERY_KEYS = [
    "setup-review",
    "update",
    "detail",
    "drafts",
    "worktrees",
    "git-pane",
    "source-trail",
    "trace",
    "timeline",
    "notification-log",
    "icons",
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
        self.assertGreaterEqual(len(ids), 14)
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

    def _screens_block(self) -> str:
        match = re.search(r"export const SCREENS = \{(.*?)\n\} as const", self.source, re.S)
        assert match is not None
        return match.group(1)

    def test_gallery_order(self):
        match = re.search(
            r"export const GALLERY: readonly ScreenName\[\] = \[(.*?)\n\]",
            self.source,
            re.S,
        )
        assert match is not None
        self.assertEqual(re.findall(r'"([^"]+)"', match.group(1)), GALLERY_KEYS)

    def test_every_gallery_screen_is_complete(self):
        block = self._screens_block()
        for key in GALLERY_KEYS:
            with self.subTest(screen=key):
                pattern = rf'"?{re.escape(key)}"?: \{{(.*?)\n  \}}'
                match = re.search(pattern, block, re.S)
                assert match is not None, f"{key} missing from SCREENS"
                entry = match.group(1)
                self.assertIn('alt: "', entry)
                self.assertIn('caption: "', entry)

    def test_hero_composite_is_wide(self):
        match = re.search(r"export const HERO_COMPOSITE: Screen = \{(.*?)\n\}", self.source, re.S)
        assert match is not None
        block = match.group(1)
        self.assertIn('file: "lpui-hero"', block)
        self.assertIn("width: 2400", block)
        self.assertIn("height: 1200", block)
        self.assertIn('alt: "', block)


class TestStoryCopy(unittest.TestCase):
    def test_copy_leads_with_plan_dispatch_proof(self):
        source = COPY.read_text(encoding="utf-8")
        self.assertIn('title: ["Plan it.", "Dispatch it.", "Prove it."]', source)
        self.assertIn("One plan. Many lanes. Proof attached.", source)
        self.assertIn("The work leaves a trail.", source)

    @unittest.skipUnless(has_built_site(), "site not built")
    def test_section_copy_is_rendered(self):
        page = page_html()
        for phrase in (
            "One plan. Many lanes. Proof attached.",
            "Every row is a workspace.",
            "A wizard, not a config file.",
            "Milestones are lanes. Lanes run in waves.",
            "The app, in use.",
            "Plan, dispatch, prove.",
            "Get the plan into your terminal.",
            "Bring your plan into focus.",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, page)


class TestPublishedCaptures(unittest.TestCase):
    def setUp(self):
        self.source = SCREENS.read_text(encoding="utf-8")

    def _size(self, name: str) -> tuple[int, int]:
        data = (SCREENS_DIR / name).read_bytes()
        self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
        width, height = struct.unpack(">II", data[16:24])
        return width, height

    def _entries(self, block: str) -> list[tuple[str, str, str]]:
        return re.findall(
            r'file: "([^"]+)",\s*width: (\d+),\s*height: (\d+),',
            block,
            re.S,
        )

    def test_story_capture_dimensions_match_the_data(self):
        block = re.search(
            r"export const SCREENS = \{(.*?)\n\} as const",
            self.source,
            re.S,
        )
        assert block is not None
        entries = self._entries(block.group(1))
        self.assertEqual(len(entries), 14)
        for file, width, height in entries:
            with self.subTest(file=file):
                self.assertEqual(self._size(f"{file}.png"), (int(width), int(height)))
                self.assertTrue((SCREENS_DIR / f"{file}.webp").is_file())

    def test_hero_composite_dimensions_match_the_data(self):
        block = re.search(
            r"export const HERO_COMPOSITE: Screen = \{(.*?)\n\}",
            self.source,
            re.S,
        )
        assert block is not None
        match = re.search(
            r'file: "([^"]+)",\s*width: (\d+),\s*height: (\d+),',
            block.group(1),
            re.S,
        )
        assert match is not None
        file, width, height = match.groups()
        self.assertEqual(self._size(f"{file}.png"), (int(width), int(height)))
        self.assertTrue((SCREENS_DIR / f"{file}.webp").is_file())


if __name__ == "__main__":
    unittest.main()
