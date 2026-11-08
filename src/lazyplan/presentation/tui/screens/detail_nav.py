"""Detail navigation: source trail and history-aware back."""

from __future__ import annotations

from typing import Any


class DetailNavigationMixin:
    """Keep detail's provenance and back keys out of the form body."""

    dkind: str
    doid: int
    _dstore: Any
    _editing: bool
    app: Any

    def _is_dirty(self) -> bool:
        return False

    def action_open_source(self) -> None:
        """Open the read-only source trail for this row."""
        opener = getattr(self.app, "open_source", None)
        if callable(opener):
            opener(self.dkind, self.doid)
            return
        from .source import SourceScreen

        self.app.push_screen(SourceScreen(self._dstore, self.dkind, self.doid))

    def action_open_trust_hubs(self) -> None:
        """Open the criteria hub for this row (palette reaches the rest)."""
        from .hub_kinds import CriteriaHub

        self.app.push_screen(CriteriaHub(self._dstore, self.dkind, self.doid))

    def action_back(self) -> None:
        """Leave detail, confirming before discarding an unsaved edit."""
        if self._editing and self._is_dirty():
            from .forms import ConfirmScreen

            def cb(confirmed: bool | None) -> None:
                if confirmed:
                    self.app.action_history_back()

            self.app.push_screen(
                ConfirmScreen(
                    "Discard your unsaved changes?",
                    confirm_label="Discard",
                    variant="warning",
                ),
                cb,
            )
            return
        self.app.action_history_back()
