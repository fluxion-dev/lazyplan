"""Textual app: filters."""

from __future__ import annotations

try:
    from textual.widgets import Tree

    from .query import query_one_opt

    _TEXTUAL_OK = True
except ImportError:  # pragma: no cover
    _TEXTUAL_OK = False

from .base import AppBase
from .screens import (
    FilterPromptScreen,
)
from .state import next_mode

if _TEXTUAL_OK:

    class FilterMixin(AppBase):
        """Plan-mode cycle and text filter."""

        def _open_filter_prompt(self) -> None:
            """Prompt for tree filter text; empty clears the filter."""

            def cb(text: str | None) -> None:
                if text is None:
                    return
                self.filter_text = text
                self._pending_note = f"filter: {text}" if text else "filter cleared"
                try:
                    self.rev += 1
                except Exception:
                    self.refresh_all(self._pending_note)

            self.push_screen(FilterPromptScreen(), cb)

        def action_cycle_mode(self) -> None:
            """Cycle Active, Finished, and Both plans."""
            self.plan_mode = next_mode(self.plan_mode)
            self.refresh_all(f"plan mode: {self.plan_mode.value}")

        def action_filter_text(self) -> None:
            """Prompt for filter text (slash)."""
            self._open_filter_prompt()

        def action_clear_filter(self) -> None:
            if len(self.screen_stack) > 1:
                return
            if self.filter_text:
                self.filter_text = ""
                self._pending_note = "filter cleared"
                try:
                    self.rev += 1
                except Exception:
                    self.refresh_all("filter cleared")
                tree = query_one_opt(self, "#tree", Tree)
                if tree is not None:
                    tree.focus()
