"""Open the trust hubs from the tree."""

from __future__ import annotations

from typing import Any

from .screens.forms import FilterPromptScreen
from .screens.hub_kinds import CriteriaHub, EvidenceHub, QuestionsHub, ReferencesHub


class HubMixin:
    """Typed actions that push each trust hub with its parent context."""

    store: Any
    app: Any
    selected: tuple[str, int] | None
    _plan_ctx: Any

    def _hub_selection(self) -> tuple[str, int] | None:
        if self.selected is None:
            self.app.notify("select a row first", timeout=3)
            return None
        return self.selected

    def action_open_criteria_hub(self) -> None:
        selected = self._hub_selection()
        if selected is not None:
            self.app.push_screen(CriteriaHub(self.store, selected[0], selected[1]))

    def action_open_questions_hub(self) -> None:
        plan_id = self._plan_ctx()
        if plan_id is None:
            self.app.notify("select a plan first", timeout=3)
            return
        self.app.push_screen(QuestionsHub(self.store, plan_id))

    def action_open_references_hub(self) -> None:
        plan_id = self._plan_ctx()
        if plan_id is None:
            self.app.notify("select a plan first", timeout=3)
            return
        self.app.push_screen(ReferencesHub(self.store, plan_id))

    def action_open_evidence_hub(self) -> None:
        def cb(text: str | None) -> None:
            if not text:
                return
            try:
                criterion_id = int(text)
            except ValueError:
                self.app.notify("criterion id must be a number", timeout=3)
                return
            self.app.push_screen(EvidenceHub(self.store, criterion_id))

        self.app.push_screen(FilterPromptScreen("Open evidence hub", "criterion id", "Open"), cb)

    def action_open_claims_hub(self) -> None:
        from .screens.hub_coordination import ClaimsHub

        selected = self._hub_selection()
        if selected is None:
            return
        kind, oid = selected
        plan_id = self._plan_ctx()
        task_id = oid if kind == "task" else None
        self.app.push_screen(ClaimsHub(self.store, task_id=task_id, plan_id=plan_id))

    def action_open_comments_hub(self) -> None:
        from .screens.hub_coordination import CommentsHub

        selected = self._hub_selection()
        if selected is not None:
            self.app.push_screen(CommentsHub(self.store, selected[0], selected[1]))

    def action_open_pull_requests_hub(self) -> None:
        from .screens.hub_provenance import PullRequestHub

        selected = self._hub_selection()
        if selected is not None:
            self.app.push_screen(PullRequestHub(self.store, selected[0], selected[1]))

    def action_open_activity_hub(self) -> None:
        from .screens.hub_provenance import ActivityHub

        self.app.push_screen(ActivityHub(self.store))

    def action_open_maintenance(self) -> None:
        from .screens.maintenance import MaintenanceScreen

        self.app.push_screen(MaintenanceScreen(self.store))
