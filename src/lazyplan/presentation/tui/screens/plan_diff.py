"""Read-only plan-scope diff: grouped changes, before/after, and reasons."""

from __future__ import annotations

try:
    from textual.app import ComposeResult  # noqa: F401
    from textual.binding import Binding  # noqa: F401
    from textual.containers import Vertical, VerticalScroll  # noqa: F401
    from textual.screen import Screen  # noqa: F401
    from textual.widgets import Label, Static  # noqa: F401

    _TEXTUAL_OK = True
except ImportError:  # pragma: no cover
    _TEXTUAL_OK = False

from ....services.revisions import DiffResult
from ...shared.design import action_bar
from ..views.diff import build_plan_diff, render_plan_diff

if _TEXTUAL_OK:

    class PlanDiffScreen(Screen):
        """Grouped scope drift with a scrollable, read-only body."""

        BINDINGS = [
            Binding("escape", "back", "Back", priority=True),
            Binding("q", "back", "Quit", priority=True),
        ]

        def __init__(self, result: DiffResult) -> None:
            super().__init__()
            self._view = build_plan_diff(result)

        def compose(self) -> ComposeResult:
            with Vertical(id="plan-diff-page"):
                yield Static("", id="plan-diff-head")
                with VerticalScroll(id="plan-diff-scroll"):
                    yield Static("", id="plan-diff-body")
                yield Label("", id="plan-diff-hints")

        def on_mount(self) -> None:
            self.query_one("#plan-diff-page").border_title = " plan diff "
            head, body = render_plan_diff(self._view)
            self.query_one("#plan-diff-head", Static).update(head)
            self.query_one("#plan-diff-body", Static).update(body)
            self.query_one("#plan-diff-hints", Label).update(
                action_bar(None, [("↑↓", "scroll"), ("esc", "back")])
            )
            self.query_one("#plan-diff-scroll", VerticalScroll).focus()

        def action_back(self) -> None:
            """Return to the plan tree."""
            self.app.pop_screen()
