"""Roadmap doc and site drift tests."""

from __future__ import annotations

import importlib.util
import re
import shutil
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

from tests.support.paths import ROOT

DOC = ROOT / "docs" / "product" / "roadmap.md"
SITE = ROOT / "site" / "roadmap.html"
HORIZONS = ("Now", "Next", "Later")

ID_RE = re.compile(r"^#### (R\d+) — ", re.MULTILINE)
HORIZON_RE = re.compile(r"^### (Now|Next|Later) — ", re.MULTILINE)
SITE_HORIZON_RE = re.compile(r'data-roadmap-horizon="(Now|Next|Later)"')
SITE_PAIR_RE = re.compile(r'data-roadmap-id="(R\d+)"\s+data-roadmap-horizon="(Now|Next|Later)"')

SPEC = importlib.util.spec_from_file_location("check_site", ROOT / "tools" / "check-site.py")
assert SPEC is not None and SPEC.loader is not None
check_site = importlib.util.module_from_spec(SPEC)
sys.modules["check_site"] = check_site
SPEC.loader.exec_module(check_site)


def doc_items() -> dict[str, str]:
    """Map each stable item ID to the horizon heading that owns it."""
    items: dict[str, str] = {}
    current: str | None = None
    for line in DOC.read_text(encoding="utf-8").splitlines():
        horizon = HORIZON_RE.match(line)
        if horizon:
            current = horizon.group(1)
            continue
        item = ID_RE.match(line)
        if item and current:
            items[item.group(1)] = current
    return items


def site_items() -> dict[str, str]:
    """Map each site card ID to its declared horizon."""
    return dict(SITE_PAIR_RE.findall(SITE.read_text(encoding="utf-8")))


class TestRoadmapSync(unittest.TestCase):
    def test_doc_declares_every_horizon(self):
        text = DOC.read_text(encoding="utf-8")
        self.assertEqual(set(HORIZON_RE.findall(text)), set(HORIZONS))

    def test_site_declares_every_horizon(self):
        text = SITE.read_text(encoding="utf-8")
        self.assertEqual(set(SITE_HORIZON_RE.findall(text)), set(HORIZONS))

    def test_item_sets_match(self):
        self.assertEqual(set(doc_items()), set(site_items()))

    def test_horizon_assignment_matches(self):
        self.assertEqual(doc_items(), site_items())

    def test_site_links_to_the_canonical_roadmap(self):
        text = SITE.read_text(encoding="utf-8")
        self.assertIn(
            "https://github.com/fluxion-dev/lazyplan/blob/main/docs/product/roadmap.md",
            text,
        )

    def test_site_links_to_the_context(self):
        text = SITE.read_text(encoding="utf-8")
        self.assertIn(
            "https://github.com/fluxion-dev/lazyplan/blob/main/docs/product/roadmap-context.md",
            text,
        )

    def test_site_links_to_the_metaplan(self):
        text = SITE.read_text(encoding="utf-8")
        self.assertIn(
            "https://github.com/fluxion-dev/lazyplan/blob/main/docs/product/roadmap-metaplan.md",
            text,
        )

    def test_sitemap_lists_the_roadmap(self):
        sitemap = (ROOT / "site" / "public" / "sitemap.xml").read_text(encoding="utf-8")
        self.assertIn("https://fluxion-dev.github.io/lazyplan/roadmap.html", sitemap)

    def test_roadmap_page_passes_the_site_gate(self):
        version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"][
            "version"
        ]
        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp) / "site"
            site.mkdir()
            shutil.copy2(SITE, site / "roadmap.html")
            shutil.copytree(ROOT / "site" / "public", site / "public")
            self.assertEqual(check_site._check_roadmap_page(site, version), [])


if __name__ == "__main__":
    unittest.main()
