"""Static contract for the marketing landing page navigation."""

from __future__ import annotations

import unittest
from html.parser import HTMLParser

from tests.support.site import has_built_site, page_html

DOCS = "https://github.com/fluxion-dev/lazyplan/blob/main/docs/usage.md"
EXPECTED_HREFS = {
    "#top",
    "#story",
    "#features",
    "#proof",
    "#screens",
    "#faq",
    "#install",
} | {DOCS}
DESKTOP_LINKS = {"#story", "#features", "#proof", "#screens", "#faq", DOCS, "#install"}


class NavParser(HTMLParser):
    """Collect nav links, ids, classes, and accessible labels."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[str] = []
        self.ids: list[str] = []
        self.classes: list[str] = []
        self.labels: list[str] = []
        self._in_nav = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        data = {key: value or "" for key, value in attrs}
        if tag == "nav" and data.get("aria-label") == "Primary":
            self._in_nav = True
        if not self._in_nav:
            return
        if data.get("id"):
            self.ids.append(data["id"])
        if data.get("class"):
            self.classes.append(data["class"])
        if data.get("aria-label"):
            self.labels.append(data["aria-label"])
        if tag == "a":
            self.links.append(data.get("href", ""))

    def handle_endtag(self, tag: str) -> None:
        if tag == "nav" and self._in_nav:
            self._in_nav = False


@unittest.skipUnless(has_built_site(), "site not built")
class TestPrimaryNavigation(unittest.TestCase):
    def setUp(self):
        self.page = page_html()
        self.parser = NavParser()
        self.parser.feed(self.page)

    def test_desktop_links_are_exact(self):
        self.assertEqual(set(self.parser.links), EXPECTED_HREFS)

    def test_every_destination_is_preserved(self):
        self.assertTrue(
            EXPECTED_HREFS <= set(self.parser.links),
            f"missing destinations: {sorted(EXPECTED_HREFS - set(self.parser.links))}",
        )

    def test_ids_are_unique(self):
        ids = [value for value in self.page.split('id="')[1:]]
        ids = [value.split('"', 1)[0] for value in ids]
        self.assertEqual(len(ids), len(set(ids)))

    def test_install_is_an_action(self):
        self.assertGreaterEqual(self.parser.links.count("#install"), 1)
        self.assertGreaterEqual(self.page.count('href="#install"'), 3)

    def test_mobile_trigger_opens_the_menu(self):
        self.assertIn(
            "Open menu",
            self.parser.labels,
            "the md:hidden sheet trigger needs an accessible name",
        )
        self.assertTrue(
            any("md:hidden" in classes for classes in self.parser.classes),
            "the mobile trigger must hide on desktop",
        )

    def test_no_link_targets_a_removed_doc(self):
        for name in (
            "setup",
            "architecture",
            "design-system",
            "performance",
            "downloads",
            "releasing",
        ):
            self.assertNotIn(f"docs/{name}.md", self.page)
        self.assertNotIn("docs/product/roadmap.md", self.page)

    def test_no_wrapping_flat_nav(self):
        nav = self.page.split('<nav aria-label="Primary"', 1)[1].split("</nav>", 1)[0]
        self.assertNotIn("flex-wrap", nav)
        self.assertIn("md:flex", nav)
        self.assertIn("md:hidden", nav)


if __name__ == "__main__":
    unittest.main()
