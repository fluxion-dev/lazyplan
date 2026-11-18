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

    def select_row(self, kind: str, oid: int) -> None: ...

    def _nav_label(self, kind: str, oid: int) -> str:
        """Human label for one row, including its ancestors."""
        full = self.store.get_full(kind, oid)
        if full is None:
            return f"{kind} #{oid}"
        obj = dict(full.get(kind, {}))
        title = str(obj.get("title", obj.get("name", ""))).strip()
        return f"{kind} {oid} {title}".strip()

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

    def open_draft(self, draft_id: int, record: bool = True) -> None:
        """Open the draft review screen and remember it in history."""
        from .screens.draft import DraftScreen

        if record:
            draft = self.store.get_draft(draft_id)
            label = f"D{draft_id} {draft.title}" if draft is not None else f"draft #{draft_id}"
            self.state.history.push(NavEntry("draft", "draft", draft_id, label))
        self.app.push_screen(DraftScreen(self.store, draft_id))

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
        if entry.screen == "source":
            self.open_source(kind, oid, record=False)
        elif entry.screen == "draft":
            self.open_draft(oid, record=False)
