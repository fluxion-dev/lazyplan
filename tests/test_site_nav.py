"""Static contract for the collapsed primary navigation."""

from __future__ import annotations

import unittest
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

EXPECTED_HREFS = {
    "#top",
    "#whats-new",
    "#features",
    "#screens",
    "#agents",
    "#coordination",
    "#provenance",
    "#collaboration",
    "#search-bulk",
    "#imports",
    "#quickstart",
    "#faq",
    "#install",
    "https://github.com/fluxion-dev/lazyplan",
}
GROUP_LINKS = {
    "Product": {"#whats-new", "#features", "#screens", "#agents"},
    "Capabilities": {
        "#coordination",
        "#provenance",
        "#collaboration",
        "#search-bulk",
        "#imports",
    },
    "Learn": {"#quickstart", "#faq"},
}


class NavParser(HTMLParser):
    """Collect nav details, summaries, panels, links, and ids."""

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
        parser.feed((ROOT / "site/index.html").read_text())
        self.parser = parser
        self.desktop = [
            item
            for item in parser.details
            if "nav-menu" in str(item["class"]) and "nav-mobile" not in str(item["class"])
        ]
        self.mobile = [item for item in parser.details if "nav-mobile" in str(item["class"])]

    def test_three_desktop_groups(self):
        self.assertEqual(
            [item["summary"] for item in self.desktop],
            ["Product", "Capabilities", "Learn"],
        )

    def test_group_links_are_exact(self):
        for item in self.desktop:
            links = item["links"]
            assert isinstance(links, list)
            self.assertEqual(set(links), GROUP_LINKS[str(item["summary"])])

    def test_mobile_menu_exists_and_keeps_every_destination(self):
        self.assertEqual(len(self.mobile), 1)
        self.assertEqual(self.mobile[0]["summary"], "Menu")
        self.assertIn("md:hidden", str(self.mobile[0]["class"]))
        links = self.mobile[0]["links"]
        assert isinstance(links, list)
        self.assertTrue(EXPECTED_HREFS - {"#top"} <= set(links))

    def test_every_destination_is_preserved(self):
        self.assertTrue(
            EXPECTED_HREFS <= set(self.parser.links),
            f"missing destinations: {sorted(EXPECTED_HREFS - set(self.parser.links))}",
        )

    def test_summaries_control_existing_panels(self):
        summaries = [*self.desktop, *self.mobile]
        self.assertTrue(summaries)
        for item in summaries:
            attrs = item["summary_attrs"]
            assert isinstance(attrs, dict)
            controls = str(attrs.get("aria-controls", ""))
            self.assertIn(controls, self.parser.ids)
            self.assertEqual(attrs.get("aria-expanded"), "false")
            self.assertFalse(item["open"])

    def test_ids_are_unique(self):
        self.assertEqual(len(self.parser.ids), len(set(self.parser.ids)))

    def test_install_and_github_are_actions(self):
        self.assertGreaterEqual(self.parser.links.count("#install"), 2)
        self.assertGreaterEqual(
            self.parser.links.count("https://github.com/fluxion-dev/lazyplan"), 2
        )

    def test_no_wrapping_flat_nav(self):
        html = (ROOT / "site/index.html").read_text()
        nav = html.split('<nav aria-label="Primary"', 1)[1].split("</nav>", 1)[0]
        self.assertNotIn("flex-wrap", nav)
        self.assertIn("md:flex", nav)
        self.assertIn("md:hidden", nav)


if __name__ == "__main__":
    unittest.main()
