"""Syntax spans stay semantic, complete, and cheap to repeat."""

from __future__ import annotations

import unittest

try:
    from lazyplan.presentation.tui.views.highlight import (
        clear_highlight_cache,
        highlight_line,
    )
except ImportError:  # pragma: no cover - stdlib-only interpreter
    highlight_line = None  # type: ignore[assignment]
    clear_highlight_cache = None  # type: ignore[assignment]


@unittest.skipUnless(highlight_line is not None, "pygments not installed")
class HighlightLineTest(unittest.TestCase):
    def setUp(self) -> None:
        assert clear_highlight_cache is not None
        clear_highlight_cache()

    def test_python_keyword_and_function(self) -> None:
        spans = highlight_line("app/source.py", "def trail(repo):")
        kinds = [kind for kind, _value in spans]
        self.assertEqual("".join(value for _kind, value in spans), "def trail(repo):")
        self.assertIn("keyword", kinds)
        self.assertIn("function", kinds)

    def test_json_key_and_number(self) -> None:
        spans = highlight_line("package.json", '{"a": 1}')
        by_value = {value: kind for kind, value in spans}
        self.assertEqual(by_value['"a"'], "string")
        self.assertEqual(by_value["1"], "number")

    def test_markdown_heading(self) -> None:
        spans = highlight_line("docs/usage.md", "## Heading")
        self.assertEqual(spans, (("keyword", "## Heading"),))

    def test_unknown_suffix_is_plain(self) -> None:
        self.assertEqual(
            highlight_line("data/file.weird", "plain [text]"),
            (("text", "plain [text]"),),
        )

    def test_text_is_never_lost(self) -> None:
        text = "value = '[' + \"x\"  # note"
        spans = highlight_line("app/source.py", text)
        self.assertEqual("".join(value for _kind, value in spans), text)

    def test_repeated_line_uses_cache(self) -> None:
        highlight_line("app/source.py", "def trail():")
        highlight_line("app/source.py", "def trail():")
        assert highlight_line is not None
        self.assertGreaterEqual(highlight_line.cache_info().hits, 1)


if __name__ == "__main__":
    unittest.main()
