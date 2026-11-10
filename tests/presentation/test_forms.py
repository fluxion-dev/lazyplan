"""Dialog prompt titles and compact form CSS stay intentional."""

from __future__ import annotations

import unittest
from pathlib import Path

try:
    from lazyplan.presentation.tui.screens.forms import FilterPromptScreen
except ImportError:  # pragma: no cover - stdlib-only interpreter
    FilterPromptScreen = None  # type: ignore[assignment]

CSS = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "lazyplan"
    / "presentation"
    / "tui"
    / "css"
    / "screens.tcss"
)


@unittest.skipUnless(FilterPromptScreen is not None, "textual not installed")
class PromptTitleTest(unittest.TestCase):
    def test_prompt_title_names_the_action(self) -> None:
        infer = FilterPromptScreen._infer_title
        self.assertEqual(infer("New criterion on task 1"), "CRITERION")
        self.assertEqual(infer("Approve P1? Why? (required after drift)"), "APPROVE")
        self.assertEqual(infer("Delete task #3? Why?"), "DELETE")
        self.assertEqual(infer("Start session"), "SESSION")
        self.assertEqual(infer("Link pull request"), "PULL REQUEST")
        self.assertEqual(infer("Filter tree by text (empty clears)"), "FILTER")


class DialogCssTest(unittest.TestCase):
    def test_dialog_fields_and_buttons_share_one_compact_scale(self) -> None:
        text = CSS.read_text(encoding="utf-8")
        self.assertIn("#dlg Input,\n#dlg Select {", text)
        self.assertIn("height: 3;", text)
        self.assertIn("#dlg TextArea {", text)
        self.assertIn("height: 5;", text)
        self.assertIn("#dlg Button, #help Button {", text)
        self.assertIn("height: 1;", text)


if __name__ == "__main__":
    unittest.main()
