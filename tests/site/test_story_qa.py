"""The story matches the shipped control room and override surfaces."""

from __future__ import annotations

import html
import unittest

from tests.support.docs import README, USAGE
from tests.support.paths import ROOT
from tests.support.site import has_built_site, page_html


class StoryQaTest(unittest.TestCase):
    def test_readme_covers_the_human_entry_points(self) -> None:
        for heading in ("## Install", "## First run", "## Why it differs", "## Learn more"):
            self.assertIn(heading, README)
        for target in ("docs/usage.md", "CHANGELOG.md", "CONTRIBUTING.md"):
            self.assertIn(f"]({target})", README)

    def test_usage_keeps_the_manual_override_surface(self) -> None:
        self.assertIn("Manual override mode", USAGE)
        self.assertIn("lpui feed --overrides", USAGE)

    @unittest.skipUnless(has_built_site(), "site not built")
    def test_site_ships_the_control_room_screenshot(self) -> None:
        index = html.unescape(page_html())
        self.assertIn("A control room for what needs you", index)
        self.assertIn("lpui-control-room.webp", index)
        self.assertTrue((ROOT / "site" / "public" / "screens" / "lpui-control-room.png").is_file())
        self.assertTrue((ROOT / "site" / "public" / "screens" / "lpui-control-room.webp").is_file())


if __name__ == "__main__":
    unittest.main()
