"""The revisions port: approval snapshots and recorded scope changes."""

from __future__ import annotations

from typing import Protocol

from ..entities import PlanChange, PlanRevision
from .planning import PlanningPort


class RevisionsPort(PlanningPort, Protocol):
    """Approval and scope-change persistence used by the revisions service."""

    def add_revision(
        self,
        plan_id: int,
        digest: str,
        snapshot: str,
        reason: str = "",
        change_mark: int = 0,
        enforced: bool = False,
        actor: str = "human",
    ) -> PlanRevision: ...

    def latest_revision(self, plan_id: int) -> PlanRevision | None: ...

    def latest_revisions_map(self) -> dict[int, PlanRevision]: ...

    def list_revisions(self, plan_id: int) -> list[PlanRevision]: ...

    def add_plan_change(
        self,
        plan_id: int,
        kind: str,
        obj_id: int,
        action: str,
        field: str = "",
        reason: str = "",
        detail: str = "",
        actor: str = "human",
    ) -> PlanChange: ...

    def list_plan_changes(self, plan_id: int, after_id: int = 0) -> list[PlanChange]: ...

    def max_change_id(self, plan_id: int) -> int: ...

    def drift_counts(self) -> dict[int, int]: ...

    def plan_drift(self, plan_id: int) -> int: ...
