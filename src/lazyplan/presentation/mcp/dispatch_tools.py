"""Dispatch MCP tool: the read-only lane manifest plus host profiles."""

from __future__ import annotations

from lazyplan.infrastructure.profiles import dispatch_profiles
from lazyplan.services import dispatch as dispatch_service

from .base import McpBase


class DispatchToolsMixin(McpBase):
    """Read-only dispatch tool."""

    def _tool_dispatch(self, args: dict) -> object:
        lane = args.get("lane")
        budget = args.get("max_chars")
        store = self._need_store()
        manifest = dispatch_service.build(
            store,
            int(args["plan"]),
            lane_id=int(lane) if lane else None,
            max_chars=int(budget) if isinstance(budget, int) else 4000,
        )
        manifest["profiles"] = dispatch_profiles(store.db_path)
        for item in manifest["dispatchable"]:
            item["profile"] = manifest["profiles"].get(item["role"], {})
        return manifest
