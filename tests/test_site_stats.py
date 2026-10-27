"""Static contract for the PyPI download stat strip."""

from __future__ import annotations

import html
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class TestDownloadStats(unittest.TestCase):
    def setUp(self):
        self.page = (ROOT / "site/index.html").read_text(encoding="utf-8")

    def test_strip_is_hidden_until_data_loads(self):
        self.assertIn('id="download-stats"', self.page)
        strip = self.page.split('id="download-stats"', 1)[1].split(">", 1)[0]
        self.assertIn("hidden", strip)
        self.assertIn('aria-label="PyPI download stats"', self.page)
        for field in ("stats-total", "stats-week", "stats-updated"):
            self.assertIn(f'id="{field}"', self.page)

    def test_caveat_and_labels_are_explicit(self):
        self.assertIn("PyPI downloads", self.page)
        self.assertIn("Last 7 days", self.page)
        self.assertIn("Excluding mirrors", self.page)
        self.assertIn("Includes CI and repeat installs", self.page)

    def test_renderer_is_same_origin_and_stale_safe(self):
        self.assertIn("fetch('downloads.json'", self.page)
        self.assertIn("var MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000;", self.page)
        self.assertIn("data.available !== true", self.page)
        self.assertNotIn("pypistats.org", self.page)
        self.assertNotIn("https://img.shields.io/pypi/d", self.page)

    def test_pages_refreshes_daily_and_json_is_generated(self):
        workflow = (ROOT / ".github/workflows/pages.yml").read_text(encoding="utf-8")
        self.assertIn("schedule:", workflow)
        self.assertIn("cron:", workflow)
        self.assertIn("tools/fetch-downloads.py", workflow)
        self.assertIn(
            "site/public/downloads.json",
            (ROOT / ".gitignore").read_text(encoding="utf-8"),
        )

    def test_page_stays_within_budget_with_stats(self):
        text = html.unescape(
            re.sub(r"<[^>]+>", " ", re.sub(r"<script.*?</script>", "", self.page, flags=re.S))
        )
        self.assertLessEqual(len(text.split()), 750)
        self.assertEqual(self.page.count("<figure"), 5)


if __name__ == "__main__":
    unittest.main()
