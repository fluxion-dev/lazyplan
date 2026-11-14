"""The insights read port: events over the provenance read surface."""

from __future__ import annotations

from typing import Protocol

from .agents import AgentsReadPort
from .claims import ClaimsReadPort
from .provenance import ProvenancePort
from .refs import RefsPort
from .revisions import RevisionsPort
from .sessions import SessionsReadPort


class InsightsPort(
    ProvenancePort,
    RevisionsPort,
    AgentsReadPort,
    RefsPort,
    ClaimsReadPort,
    SessionsReadPort,
    Protocol,
):
    """Read-only surface used by metrics, stats, audit, brief, and lint."""

    def events_by_action(self, *actions: str) -> list[dict]: ...
