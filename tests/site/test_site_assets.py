"""Screenshot scene registry: coverage and shape, without ImageMagick."""

from __future__ import annotations

import importlib.util
import os
import sys
import unittest

from tests.support.paths import ROOT

if importlib.util.find_spec("rich") is None or importlib.util.find_spec("textual") is None:
    capture = None  # type: ignore[assignment]
else:
    SPEC = importlib.util.spec_from_file_location(
        "capture_screens", ROOT / "tools" / "capture-screens.py"
    )
    assert SPEC is not None and SPEC.loader is not None
    capture = importlib.util.module_from_spec(SPEC)
    sys.modules["capture_screens"] = capture
    SPEC.loader.exec_module(capture)

EXPECTED = {
    "lpui-detail",
    "lpui-source-trail",
    "lpui-coordination",
    "lpui-collaboration",
    "lpui-search-bulk",
    "lpui-bulk-palette",
    "lpui-flow-health",
    "lpui-trace",
    "lpui-mcp",
    "lpui-share-sync",
    "lpui-gates",
    "lpui-imports",
}


@unittest.skipUnless(capture is not None, "rich and textual required")
class TestSceneRegistry(unittest.TestCase):
    def test_every_capability_scene_is_registered(self):
        self.assertEqual(set(capture.SCENES), EXPECTED)

    def test_scenes_are_complete(self):
        for name, scene in capture.SCENES.items():
            with self.subTest(scene=name):
                self.assertEqual(len(scene.size), 2)
                self.assertGreater(scene.size[0], 0)
                self.assertGreater(scene.size[1], 0)
                self.assertTrue(callable(scene.build))
                self.assertTrue(callable(scene.capture))
                self.assertGreater(len(scene.alt), 30)
                self.assertNotIn("lorem", scene.alt.lower())

    def test_output_names_are_stable(self):
        for name in capture.SCENES:
            self.assertRegex(name, r"^lpui-[a-z0-9-]+$")

    def test_transcript_scenes_do_not_need_a_fixture(self):
        for name in (
            "lpui-flow-health",
            "lpui-trace",
            "lpui-mcp",
            "lpui-share-sync",
            "lpui-gates",
            "lpui-imports",
        ):
            with self.subTest(scene=name):
                self.assertIsNone(capture.SCENES[name].build(ROOT))

    def test_social_card_target_is_stable(self):
        self.assertEqual(capture.DEFAULT_OUT, ROOT / "site" / "public" / "screens")
        self.assertEqual(os.path.basename("og-lpui-and-agent.png"), "og-lpui-and-agent.png")


if __name__ == "__main__":
    unittest.main()
