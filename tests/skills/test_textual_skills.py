"""Coverage contract for the repo-local Textual skill suite."""

from __future__ import annotations

import importlib.util
import json
import sys
import unittest

from tests.support.paths import ROOT

try:
    import textual  # noqa: F401

    _TEXTUAL_OK = True
except ImportError:  # stdlib-only interpreter
    _TEXTUAL_OK = False

SPEC = importlib.util.spec_from_file_location(
    "gen_textual_skills", ROOT / "tools" / "gen_textual_skills.py"
)
assert SPEC is not None and SPEC.loader is not None
GEN = importlib.util.module_from_spec(SPEC)
sys.modules["gen_textual_skills"] = GEN
SPEC.loader.exec_module(GEN)

MANIFEST = ROOT / ".agents/skills/textual/references/_manifest.json"


@unittest.skipUnless(_TEXTUAL_OK, "textual not installed")
class TestTextualSkillCoverage(unittest.TestCase):
    def setUp(self):
        self.data = json.loads(MANIFEST.read_text(encoding="utf-8"))

    def test_checker_passes(self):
        self.assertEqual(GEN.check(), 0)

    def test_every_reference_category_is_counted(self):
        counts = {name: entry["count"] for name, entry in self.data["categories"].items()}
        self.assertEqual(
            counts,
            {
                "widgets": 37,
                "styles": 68,
                "events": 27,
                "css-types": 16,
                "layout": 14,
                "guides": 18,
            },
        )
        self.assertEqual(len(self.data["items"]), 180)

    def test_every_guide_is_present(self):
        guides = {item["id"] for item in self.data["items"] if item["category"] == "guides"}
        self.assertEqual(
            guides,
            {
                "devtools",
                "app",
                "styles",
                "css",
                "queries",
                "layout",
                "events",
                "input",
                "actions",
                "reactivity",
                "design",
                "widgets",
                "content",
                "animation",
                "screens",
                "workers",
                "command_palette",
                "testing",
            },
        )

    def test_every_item_has_a_file_and_source(self):
        for item in self.data["items"]:
            with self.subTest(item=item["id"]):
                self.assertTrue((ROOT / item["file"]).is_file())
                self.assertTrue(item["source"].startswith("https://textual.textualize.io/"))

    def test_router_links_every_category(self):
        router = (ROOT / ".agents/skills/textual/SKILL.md").read_text(encoding="utf-8")
        for entry in self.data["categories"].values():
            self.assertIn(f"../{entry['skill']}/SKILL.md", router)


if __name__ == "__main__":
    unittest.main()
