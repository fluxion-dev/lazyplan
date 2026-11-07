"""The insights read port: events, rows, links, claims, and annotations."""

from __future__ import annotations

from typing import Protocol

from ..entities import Claim
from .provenance import ProvenancePort
from .revisions import RevisionsPort


class InsightsPort(ProvenancePort, RevisionsPort, Protocol):
    """Read-only surface used by metrics, stats, audit, brief, and lint."""

    def feed(self, limit: int = 20) -> list[dict]: ...

    def events_by_action(self, *actions: str) -> list[dict]: ...

    def claims_map(self) -> dict[int, Claim]: ...

    def get_claim(self, task_id: int) -> Claim | None: ...

    def list_claims(
        self,
        include_expired: bool = False,
        now: float | None = None,
        plan_id: int | None = None,
    ) -> list[dict]: ...

    def open_task_criteria_ids(self) -> set[int]: ...

    def all_criterion_links(self) -> list[dict]: ...
