"""The coordination repository port: leases, blocked work, and touch-points."""

from __future__ import annotations

from typing import Protocol

from .claims import BlockedPort, ClaimsPort
from .collaboration import CollaborationPort
from .repos import ReposPort
from .touchpoints import TouchpointPort


class CoordinationPort(
    ReposPort,
    CollaborationPort,
    TouchpointPort,
    ClaimsPort,
    BlockedPort,
    Protocol,
):
    """Claim, blocked-work, and touch-point surface, composed from capabilities."""
