"""Screenshot zoom: every screen links to its full-size image and a dialog."""

from __future__ import annotations

import re
import unittest

from tests.support.paths import ROOT
from tests.support.site import has_built_site, page_html

TRIGGERS = re.compile(r"<button[^>]*data-zoom[^>]*>")
IMAGES = re.compile(r'<img src="(\./screens/[^"]+\.png)"')
COMPONENT = ROOT / "site/src/components/site/screenshots.tsx"


@unittest.skipUnless(has_built_site(), "site not built")
class TestScreenshotZoom(unittest.TestCase):
    def setUp(self):
        self.page = page_html()
        self.component = COMPONENT.read_text(encoding="utf-8")

    def test_every_screenshot_is_a_zoom_trigger(self):
        self.assertEqual(len(TRIGGERS.findall(self.page)), 10)
        self.assertEqual(len(IMAGES.findall(self.page)), 10)

    def test_every_trigger_targets_a_published_png(self):
        for href in IMAGES.findall(self.page):
            with self.subTest(href=href):
                png = ROOT / "site/public" / href
                webp = png.with_suffix(".webp")
                self.assertTrue(png.is_file())
                self.assertTrue(webp.is_file())

    def test_dialog_is_shadcn_with_a_title(self):
        for fragment in ("<Dialog", "DialogContent", "DialogTitle", "data-zoom"):
            self.assertIn(fragment, self.component)

    def test_images_declare_dimensions_and_alt(self):
        for tag in re.findall(r"<img[^>]*src=\"\./screens/[^\"]+\.png\"[^>]*>", self.page):
            with self.subTest(tag=tag):
                self.assertIn(' alt="', tag)
                self.assertIn(' width="1604"', tag)
                self.assertIn(' height="904"', tag)


if __name__ == "__main__":
    unittest.main()
