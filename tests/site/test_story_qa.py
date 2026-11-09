"""The story matches the shipped control room surfaces."""

from __future__ import annotations

import unittest

from tests.support.docs import README, USAGE
from tests.support.paths import ROOT


class StoryQaTest(unittest.TestCase):
    def test_readme_covers_the_human_entry_points(self) -> None:
        for heading in ("## Install", "## First run", "## Why it differs", "## Learn more"):
            self.assertIn(heading, README)
        for target in ("docs/usage.md", "CHANGELOG.md", "CONTRIBUTING.md"):
            self.assertIn(f"]({target})", README)

    def test_usage_has_no_manual_override_surface(self) -> None:
        self.assertNotIn("Manual override mode", USAGE)
        self.assertNotIn("lpui feed --overrides", USAGE)

    def test_site_ships_the_control_room_screenshot(self) -> None:
        index = (ROOT / "site" / "index.html").read_text(encoding="utf-8")
        self.assertIn("What's new", index)
        self.assertIn("lpui-control-room.webp", index)
        self.assertTrue((ROOT / "site" / "public" / "screens" / "lpui-control-room.png").is_file())
        self.assertTrue((ROOT / "site" / "public" / "screens" / "lpui-control-room.webp").is_file())


if __name__ == "__main__":
    unittest.main()
