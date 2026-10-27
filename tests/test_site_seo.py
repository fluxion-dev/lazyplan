"""Site discoverability gate: metadata, structured data, links, and assets."""

import importlib.util
import re
import shutil
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("check_site", ROOT / "tools/check-site.py")
assert SPEC is not None and SPEC.loader is not None
check_site = importlib.util.module_from_spec(SPEC)
sys.modules["check_site"] = check_site
SPEC.loader.exec_module(check_site)


class TestSiteSEO(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.site = Path(self.tmp.name) / "site"
        self.site.mkdir()
        shutil.copy2(ROOT / "site/index.html", self.site / "index.html")
        shutil.copytree(ROOT / "site/public", self.site / "public")
        self.version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))[
            "project"
        ]["version"]

    def tearDown(self):
        self.tmp.cleanup()

    def _errors(self) -> list[str]:
        return check_site._check_page(self.site, self.version)

    def test_current_site_passes(self):
        self.assertEqual(self._errors(), [])

    def test_missing_canonical_fails(self):
        index = self.site / "index.html"
        index.write_text(
            index.read_text(encoding="utf-8").replace(
                '<link rel="canonical" href="https://fluxion-dev.github.io/lazyplan/">', ""
            ),
            encoding="utf-8",
        )
        self.assertTrue(any("canonical" in error for error in self._errors()))

    def test_broken_anchor_fails(self):
        index = self.site / "index.html"
        index.write_text(
            index.read_text(encoding="utf-8").replace('href="#faq"', 'href="#missing"'),
            encoding="utf-8",
        )
        self.assertTrue(any("broken internal anchor" in error for error in self._errors()))

    def test_missing_alt_fails(self):
        index = self.site / "index.html"
        index.write_text(
            index.read_text(encoding="utf-8").replace(
                'alt="Plan tree filtered to attention, showing active and expired claims, blocked work, aging tasks, and a red check."',
                "",
            ),
            encoding="utf-8",
        )
        self.assertTrue(any("missing alt" in error for error in self._errors()))

    def test_wrong_image_width_fails(self):
        index = self.site / "index.html"
        index.write_text(
            index.read_text(encoding="utf-8").replace(
                'width="1604" height="904"', 'width="1600" height="904"'
            ),
            encoding="utf-8",
        )
        self.assertTrue(any("width mismatch" in error for error in self._errors()))

    def test_wrong_image_height_fails(self):
        index = self.site / "index.html"
        index.write_text(
            index.read_text(encoding="utf-8").replace(
                'width="1604" height="904"', 'width="1604" height="900"'
            ),
            encoding="utf-8",
        )
        self.assertTrue(any("height mismatch" in error for error in self._errors()))

    def test_malformed_json_ld_fails(self):
        index = self.site / "index.html"
        text = index.read_text(encoding="utf-8")
        text = text.replace('"@type": "FAQPage"', '"@type": "FAQPage",,')
        index.write_text(text, encoding="utf-8")
        self.assertTrue(any("invalid JSON-LD" in error for error in self._errors()))

    def test_every_published_screen_is_referenced(self):
        html = (ROOT / "site/index.html").read_text(encoding="utf-8")
        referenced = set(re.findall(r"screens/([A-Za-z0-9._-]+)", html))
        published = {
            path.name for path in (ROOT / "site/public/screens").iterdir() if path.is_file()
        }
        self.assertEqual(published - referenced, set())
        for name in published:
            if name.endswith(".png") and not name.startswith("og-"):
                self.assertIn(name.removesuffix(".png") + ".webp", published)


if __name__ == "__main__":
    unittest.main()
