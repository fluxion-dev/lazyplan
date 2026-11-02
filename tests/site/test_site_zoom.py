"""Screenshot zoom: every screen links to its full-size image and a dialog."""

from __future__ import annotations

import re
import unittest

from tests.support.paths import ROOT

PAGE = ROOT / "site/index.html"
TRIGGERS = re.compile(
    r'<a class="zoom-trigger" href="(\./screens/[^"]+)" data-zoom aria-haspopup="dialog">',
)
IMAGES = re.compile(r'<img src="(\./screens/[^"]+\.png)"')


class TestScreenshotZoom(unittest.TestCase):
    def setUp(self):
        self.page = PAGE.read_text(encoding="utf-8")

    def test_every_screenshot_is_a_zoom_trigger(self):
        self.assertEqual(sorted(TRIGGERS.findall(self.page)), sorted(IMAGES.findall(self.page)))

    def test_every_trigger_targets_a_published_png(self):
        for href in TRIGGERS.findall(self.page):
            with self.subTest(href=href):
                png = ROOT / "site/public" / href
                webp = png.with_suffix(".webp")
                self.assertTrue(png.is_file())
                self.assertTrue(webp.is_file())

    def test_dialog_exposes_a_close_control_and_caption(self):
        for fragment in (
            '<dialog id="zoom"',
            'aria-label="Screenshot preview"',
            'id="zoom-close"',
            'aria-label="Close screenshot preview"',
            'id="zoom-image"',
            'id="zoom-caption"',
        ):
            self.assertIn(fragment, self.page)

    def test_script_opens_the_native_dialog(self):
        self.assertIn("document.querySelectorAll('[data-zoom]')", self.page)
        self.assertIn("dialog.showModal()", self.page)
        self.assertIn("dialog.close()", self.page)


if __name__ == "__main__":
    unittest.main()
