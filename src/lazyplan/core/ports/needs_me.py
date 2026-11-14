"""The needs-me read port: the control-room payload read surface."""

from __future__ import annotations

from typing import Protocol

from .insights import InsightsPort


class NeedsMePort(InsightsPort, Protocol):
    """Read surface for the control-room payload."""
