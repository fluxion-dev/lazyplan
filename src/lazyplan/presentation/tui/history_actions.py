"""App actions for history, breadcrumbs, and provenance navigation."""

from __future__ import annotations

from typing import Any

from .navigation import NavEntry


class HistoryMixin:
    """Record where the user has been and replay it on back and forward."""

    app: Any
    store: Any
    state: Any
    selected: tuple[str, int] | None

    def _open_detail(
        self, kind: str, oid: int, edit: bool = False, record: bool = True
    ) -> None: ...

    def _nav_label(self, kind: str, oid: int) -> str:
        """Human breadcrumb for one row, including its ancestors."""
        from .views.detail import detail_breadcrumb

        full = self.store.get_full(kind, oid)
        if full is None:
            return f"{kind} #{oid}"
        key = {"plan": "plan", "milestone": "milestone", "task": "task"}[kind]
        return detail_breadcrumb(self.store, kind, oid, dict(full.get(key, {})))

    def breadcrumb(self) -> str:
        """Every level visited so far, root first."""
        return str(self.state.history.breadcrumb())

    def open_source(self, kind: str, oid: int, record: bool = True) -> None:
        """Open the source trail and remember it in history."""
        from .screens.source import SourceScreen

        if record:
            label = f"{self._nav_label(kind, oid)} source"
            self.state.history.push(NavEntry("source", kind, oid, label))
        self.app.push_screen(SourceScreen(self.store, kind, oid))

    def action_history_back(self) -> None:
        """Return to the prior screen and restore its exact selection."""
        entry = self.state.history.back()
        if len(self.app.screen_stack) > 1:
            self.app.pop_screen()
        if entry is not None and entry.selection is not None:
            self.selected = entry.selection
            self.app.update_preview(force=True)

    def action_history_forward(self) -> None:
        """Replay the next history entry, including the screen."""
        entry = self.state.history.forward()
        if entry is None:
            return
        if entry.screen == "tree":
            while len(self.app.screen_stack) > 1:
                self.app.pop_screen()
            if entry.selection is not None:
                self.selected = entry.selection
            return
        if entry.selection is None:
            return
        self.selected = entry.selection
        kind, oid = entry.selection
        if entry.screen == "detail":
            self._open_detail(kind, oid, record=False)
        elif entry.screen == "source":
            self.open_source(kind, oid, record=False)
