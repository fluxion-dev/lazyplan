"""The story matches the shipped control room and override surfaces."""

from __future__ import annotations

import unittest

from tests.support.paths import ROOT


class StoryQaTest(unittest.TestCase):
    def test_roadmap_has_no_stale_coordination_or_resume_claims(self) -> None:
        text = (ROOT / "docs" / "product" / "roadmap.md").read_text(encoding="utf-8")
        self.assertNotIn("no file or worktree collision awareness", text)
        self.assertNotIn("No session memory, decision log, or plan diff", text)
        self.assertIn("Execution coordination | Strong", text)
        self.assertIn("Resume and continuity | Strong", text)

    def test_readme_and_usage_describe_the_control_room(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        usage = (ROOT / "docs" / "usage.md").read_text(encoding="utf-8")
        self.assertIn("control room", readme.lower())
        self.assertIn("Manual override mode", readme)
        self.assertIn("Manual override mode", usage)
        self.assertIn("lpui feed --overrides", usage)
        self.assertIn("Observe and Override", readme)

    def test_site_ships_the_control_room_screenshot(self) -> None:
        index = (ROOT / "site" / "index.html").read_text(encoding="utf-8")
        self.assertIn("New in 0.35", index)
        self.assertIn("lpui-control-room.webp", index)
        self.assertTrue((ROOT / "site" / "public" / "screens" / "lpui-control-room.png").is_file())
        self.assertTrue((ROOT / "site" / "public" / "screens" / "lpui-control-room.webp").is_file())


if __name__ == "__main__":
    unittest.main()
