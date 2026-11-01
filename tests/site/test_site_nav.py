"""Static contract for the marketing landing page navigation."""

from __future__ import annotations

import unittest
from html.parser import HTMLParser

from tests.support.paths import ROOT

DOCS = "https://github.com/fluxion-dev/lazyplan/blob/main/docs/usage.md"
EXPECTED_HREFS = {
    "#top",
    "#new",
    "#features",
    "#screens",
    "#faq",
    "#install",
    DOCS,
}
DESKTOP_LINKS = {"#new", "#features", "#screens", "#faq", DOCS, "#install"}


class NavParser(HTMLParser):
    """Collect nav links, details, summaries, and ids."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_nav = False
        self.details: list[dict[str, object]] = []
        self.links: list[str] = []
        self.ids: list[str] = []
        self._in_summary = False
        self._summary_text: list[str] = []
        self._details_index: int | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        data = {key: value or "" for key, value in attrs}
        if tag == "nav" and data.get("aria-label") == "Primary":
            self.in_nav = True
            return
        if not self.in_nav:
            return
        if data.get("id"):
            self.ids.append(data["id"])
        if tag == "details":
            self.details.append(
                {
                    "class": data.get("class", ""),
                    "summary": "",
                    "summary_attrs": {},
                    "open": "open" in data,
                    "links": [],
                }
            )
            self._details_index = len(self.details) - 1
        elif tag == "summary" and self.details:
            self._in_summary = True
            self._summary_text = []
            self.details[-1]["summary_attrs"] = data
        elif tag == "a":
            href = data.get("href", "")
            self.links.append(href)
            if self._details_index is not None:
                links = self.details[self._details_index]["links"]
                assert isinstance(links, list)
                links.append(href)

    def handle_data(self, data: str) -> None:
        if self._in_summary:
            self._summary_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "summary" and self._in_summary:
            if self.details:
                self.details[-1]["summary"] = " ".join(
                    part.strip() for part in self._summary_text if part.strip()
                )
            self._in_summary = False
        elif tag == "details":
            self._details_index = None
        elif tag == "nav" and self.in_nav:
            self.in_nav = False


class TestPrimaryNavigation(unittest.TestCase):
    def setUp(self):
        parser = NavParser()
        parser.feed((ROOT / "site/index.html").read_text(encoding="utf-8"))
        self.parser = parser
        self.mobile = [item for item in parser.details if "nav-mobile" in str(item["class"])]

    def test_desktop_links_are_exact(self):
        html = (ROOT / "site/index.html").read_text(encoding="utf-8")
        desktop = html.split('class="hidden items-center gap-x-6 md:flex"', 1)[1].split(
            "</div>", 1
        )[0]
        parser = NavParser()
        parser.in_nav = True
        parser.feed(desktop)
        self.assertEqual(set(parser.links), DESKTOP_LINKS)

    def test_mobile_menu_keeps_every_destination(self):
        self.assertEqual(len(self.mobile), 1)
        self.assertEqual(self.mobile[0]["summary"], "Menu")
        links = self.mobile[0]["links"]
        assert isinstance(links, list)
        self.assertEqual(set(links), {"#new", "#features", "#screens", "#faq", DOCS, "#install"})

    def test_every_destination_is_preserved(self):
        self.assertTrue(
            EXPECTED_HREFS <= set(self.parser.links),
            f"missing destinations: {sorted(EXPECTED_HREFS - set(self.parser.links))}",
        )

    def test_summary_controls_existing_panel(self):
        item = self.mobile[0]
        attrs = item["summary_attrs"]
        assert isinstance(attrs, dict)
        controls = str(attrs.get("aria-controls", ""))
        self.assertIn(controls, self.parser.ids)
        self.assertEqual(attrs.get("aria-expanded"), "false")
        self.assertFalse(item["open"])

    def test_ids_are_unique(self):
        self.assertEqual(len(self.parser.ids), len(set(self.parser.ids)))

    def test_install_is_an_action(self):
        self.assertGreaterEqual(self.parser.links.count("#install"), 2)

    def test_no_wrapping_flat_nav(self):
        html = (ROOT / "site/index.html").read_text(encoding="utf-8")
        nav = html.split('<nav aria-label="Primary"', 1)[1].split("</nav>", 1)[0]
        self.assertNotIn("flex-wrap", nav)
        self.assertIn("md:flex", nav)
        self.assertIn("md:hidden", nav)


if __name__ == "__main__":
    unittest.main()
