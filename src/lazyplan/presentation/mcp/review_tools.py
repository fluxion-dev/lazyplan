"""MCP review tool."""

from __future__ import annotations

from typing import Any

from lazyplan import services

from .base import McpBase
from .handlers import review_packet
from .schema import id_schema as _id
from .schema import tool as _tool


class ReviewToolsMixin(McpBase):
    """Read-only review packet tool."""

    def _review_read_registry(self) -> dict[str, tuple[dict, Any]]:
        return {
            "review": (
                _tool(
                    "review",
                    "Deterministic Markdown review packet for one plan.",
                    {"plan": _id(), "max_chars": {"type": "integer"}},
                ),
                review_packet(self._need_store, services.build_review),
            ),
            "ship": (
                _tool(
                    "ship",
                    "Deterministic Markdown outcome ship note for one plan.",
                    {"plan": _id(), "max_chars": {"type": "integer"}},
                ),
                review_packet(self._need_store, services.build_ship),
            ),
        }
