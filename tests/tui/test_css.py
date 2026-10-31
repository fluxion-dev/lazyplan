"""The shell CSS lives in packaged modules and uses theme tokens only."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

try:
    from lazyplan import tui as tui_mod
except ImportError:  # pragma: no cover - stdlib-only interpreter
    tui_mod = None  # type: ignore[assignment]

CSS_DIR = Path(__file__).resolve().parents[2] / "src" / "lazyplan" / "tui" / "css"
COLOUR_LITERAL = re.compile(r"#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(")


@unittest.skipUnless(tui_mod is not None and tui_mod._TEXTUAL_OK, "textual not installed")
class CssModuleTest(unittest.TestCase):
    def test_shell_loads_three_css_modules(self) -> None:
        paths = [Path(path) for path in tui_mod.LazyplanApp.CSS_PATH or []]
        self.assertEqual(
            [path.name for path in paths], ["app.tcss", "components.tcss", "screens.tcss"]
        )
        for path in paths:
            self.assertTrue(path.is_file(), path)

    def test_css_uses_theme_tokens_instead_of_colour_literals(self) -> None:
        for path in CSS_DIR.glob("*.tcss"):
            text = path.read_text(encoding="utf-8")
            self.assertIsNone(COLOUR_LITERAL.search(text), path)
        shell = (CSS_DIR / "app.tcss").read_text(encoding="utf-8")
        self.assertIn("$lp-border", shell)
        self.assertIn("$lp-text-muted", shell)

    def test_css_modules_are_packaged(self) -> None:
        pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
        text = pyproject.read_text(encoding="utf-8")
        self.assertIn("tui/css/*.tcss", text)


if __name__ == "__main__":
    unittest.main()
