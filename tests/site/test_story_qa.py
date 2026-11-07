"""The story matches the shipped control room and override surfaces."""

from __future__ import annotations

import unittest

from tests.support.docs import README, USAGE
from tests.support.paths import ROOT


class StoryQaTest(unittest.TestCase):
    def test_roadmap_has_no_stale_coordination_or_resume_claims(self) -> None:
        text = (ROOT / "docs" / "product" / "roadmap.md").read_text(encoding="utf-8")
        self.assertNotIn("no file or worktree collision awareness", text)
        self.assertNotIn("No session memory, decision log, or plan diff", text)
        self.assertIn("Execution coordination | Strong", text)
        self.assertIn("Resume and continuity | Strong", text)

    def test_readme_covers_the_human_entry_points(self) -> None:
        for heading in ("## Install", "## First run", "## Why it differs", "## Learn more"):
            self.assertIn(heading, README)
        for target in ("docs/usage.md", "CHANGELOG.md", "CONTRIBUTING.md"):
            self.assertIn(f"]({target})", README)

    def test_usage_keeps_the_manual_override_surface(self) -> None:
        self.assertIn("Manual override mode", USAGE)
        self.assertIn("lpui feed --overrides", USAGE)

    def test_site_ships_the_control_room_screenshot(self) -> None:
        index = (ROOT / "site" / "index.html").read_text(encoding="utf-8")
        self.assertIn("New in 0.35", index)
        self.assertIn("lpui-control-room.webp", index)
        self.assertTrue((ROOT / "site" / "public" / "screens" / "lpui-control-room.png").is_file())
        self.assertTrue((ROOT / "site" / "public" / "screens" / "lpui-control-room.webp").is_file())


if __name__ == "__main__":
    unittest.main()
