"""The MCP tool port: planning, provenance, transfer, and coordination."""

from __future__ import annotations

from typing import Protocol

from .coordination import CoordinationPort
from .insights import InsightsPort
from .transfer import TransferPort


class McpPort(TransferPort, CoordinationPort, InsightsPort, Protocol):
    """Every read and write surface the MCP tool table exposes."""
