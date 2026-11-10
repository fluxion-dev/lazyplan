"""Shell defaults that should not drift back into the launch state."""

from __future__ import annotations

import unittest

try:
    from lazyplan.presentation.tui.state import AppState
except ImportError:  # pragma: no cover - stdlib-only interpreter
    AppState = None  # type: ignore[assignment]


@unittest.skipUnless(AppState is not None, "textual not installed")
class ShellDefaultsTest(unittest.TestCase):
    def test_timeline_stays_hidden_at_launch(self) -> None:
        state = AppState()
        self.assertFalse(state.timeline_visible)
        self.assertFalse(state.timeline_shown(narrow=False))
        self.assertFalse(state.timeline_shown(narrow=True))


if __name__ == "__main__":
    unittest.main()
