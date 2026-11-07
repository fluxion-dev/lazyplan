"""The references port: read-only external links on a plan."""

from __future__ import annotations

from typing import Protocol

from ..entities import ExternalRef
from .planning import PlanningPort


class RefsPort(PlanningPort, Protocol):
    """External reference persistence used by the ref commands and reads."""

    def link_ref(
        self,
        plan_id: int,
        url: str,
        provider: str = "",
        kind: str = "issue",
        external_id: str = "",
        title: str = "",
        state: str = "",
        actor: str = "human",
        now: float | None = None,
    ) -> ExternalRef: ...

    def list_refs(self, plan_id: int) -> list[ExternalRef]: ...

    def refs_map(self) -> dict[int, list[ExternalRef]]: ...

    def unlink_ref(
        self,
        plan_id: int,
        ref_id: int = 0,
        url: str = "",
        actor: str = "human",
    ) -> bool: ...
