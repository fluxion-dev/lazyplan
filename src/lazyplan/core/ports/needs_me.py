"""The needs-me read port: attention, health, sessions, and claims."""

from __future__ import annotations

from typing import Protocol

from .insights import InsightsPort


class TouchpointReadPort(Protocol):
    """Read-only touch-point lookup used for overlap checks."""

    def touchpoints_map(self) -> dict[int, list[str]]: ...


class NeedsMePort(InsightsPort, TouchpointReadPort, Protocol):
    """Read surface for the control-room payload."""
