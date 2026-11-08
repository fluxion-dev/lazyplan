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

    def action_open_claims_hub(self) -> None:
        """Open claims and touch-points for this row."""
        from .hub import plan_id_for
        from .hub_coordination import ClaimsHub

        task_id = self.doid if self.dkind == "task" else None
        plan_id = plan_id_for(self._dstore, self.dkind, self.doid)
        self.app.push_screen(ClaimsHub(self._dstore, task_id=task_id, plan_id=plan_id))

    def action_open_sessions_hub(self) -> None:
        """Open sessions and handoffs for the owning plan."""
        from .hub import plan_id_for
        from .hub_coordination import SessionsHub

        plan_id = plan_id_for(self._dstore, self.dkind, self.doid)
        if plan_id is not None:
            self.app.push_screen(SessionsHub(self._dstore, plan_id))

    def action_open_comments_hub(self) -> None:
        """Open comments and notes for this row."""
        from .hub_coordination import CommentsHub

        self.app.push_screen(CommentsHub(self._dstore, self.dkind, self.doid))

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
