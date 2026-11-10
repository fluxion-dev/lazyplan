"""The broad application port used by CLI and MCP adapters."""

from __future__ import annotations

from typing import Protocol

from .coordination import CoordinationPort
from .insights import InsightsPort
from .sessions import SessionsPort
from .transfer import TransferPort


class AppPort(TransferPort, CoordinationPort, InsightsPort, SessionsPort, Protocol):
    """Every read and write surface a surface adapter may call."""
