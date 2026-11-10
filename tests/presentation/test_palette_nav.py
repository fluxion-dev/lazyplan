"""Palette navigation skips headers and wraps from the search field."""

from __future__ import annotations

import unittest

try:
    from lazyplan.presentation.tui.screens.help import PaletteScreen
except ImportError:  # pragma: no cover - stdlib-only interpreter
    PaletteScreen = None  # type: ignore[assignment]


@unittest.skipUnless(PaletteScreen is not None, "textual not installed")
class PaletteNavTest(unittest.TestCase):
    def test_next_enabled_skips_headers(self) -> None:
        disabled = [True, False, False, True]
        self.assertEqual(PaletteScreen._next_enabled(disabled, 0, 1), 1)
        self.assertEqual(PaletteScreen._next_enabled(disabled, 1, 1), 2)

    def test_next_enabled_wraps(self) -> None:
        disabled = [False, True, False]
        self.assertEqual(PaletteScreen._next_enabled(disabled, 2, 1), 0)
        self.assertEqual(PaletteScreen._next_enabled(disabled, 0, -1), 2)

    def test_next_enabled_returns_none_when_everything_is_disabled(self) -> None:
        self.assertIsNone(PaletteScreen._next_enabled([True, True], 0, 1))
        self.assertIsNone(PaletteScreen._next_enabled([], None, 1))

    def test_title_names_the_arrow_keys(self) -> None:
        title = PaletteScreen({})._title([], "")
        self.assertIn("↑/↓", title)
        self.assertIn("enter", title)


if __name__ == "__main__":
    unittest.main()
