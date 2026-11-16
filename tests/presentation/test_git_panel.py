"""The GIT pane tolerates a probe finishing before it is mounted."""

from __future__ import annotations

import unittest

try:
    from lazyplan.presentation.tui.views.git import GitDocument
    from lazyplan.presentation.tui.widgets.git_panel import GitPanel
except ImportError:  # pragma: no cover - textual not installed
    GitPanel = None  # type: ignore[assignment]
    GitDocument = None  # type: ignore[assignment]


@unittest.skipUnless(GitPanel is not None, "textual not installed")
class GitPanelMountTest(unittest.TestCase):
    def test_show_before_mount_does_not_query_a_missing_body(self) -> None:
        panel = GitPanel()
        panel.show(GitDocument(body="[bold]web[/]"))
        self.assertFalse(panel.display)

    def test_show_error_before_mount_does_not_query_a_missing_body(self) -> None:
        panel = GitPanel()
        panel.show_error("probe failed")
        self.assertFalse(panel.display)
