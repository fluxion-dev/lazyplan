"""Dispatch MCP tool: the read-only lane manifest plus host profiles."""

from __future__ import annotations

from typing import Any

from lazyplan.core.policies.context import (
    DEFAULT_CONTEXT_WINDOW,
    DEFAULT_TASK_CONTEXT_PERCENT,
)
from lazyplan.infrastructure.profiles import context_windows, dispatch_profiles
from lazyplan.services import dispatch as dispatch_service
from lazyplan.services import task_brief

from .base import McpBase
from .schema import id_schema as _id
from .schema import tool as _tool


class DispatchToolsMixin(McpBase):
    """Read-only dispatch and task-brief tools."""

    def _dispatch_read_registry(self) -> list[tuple[dict, Any]]:
        """Read tools registered beside their handlers."""
        return [
            (
                _tool(
                    "dispatch",
                    "Plan lanes, waves, capacity, worktree actions, and worker prompts.",
                    {
                        "plan": _id(),
                        "lane": _id(),
                        "max_chars": {"type": "integer"},
                        "context_percent": {"type": "integer"},
                    },
                    ["plan"],
                ),
                self._tool_dispatch,
            ),
            (
                _tool(
                    "task_brief",
                    "Fresh-session task brief with its context budget.",
                    {
                        "id": _id(),
                        "host": {"type": "string"},
                        "context_window": {"type": "integer"},
                        "percent": {"type": "integer"},
                    },
                    ["id"],
                ),
                self._tool_task_brief,
            ),
        ]

    def _tool_dispatch(self, args: dict) -> object:
        lane = args.get("lane")
        budget = args.get("max_chars")
        store = self._need_store()
        profiles = dispatch_profiles(store.db_path)
        windows = {role: int(str(row.get("context_window") or 0)) for role, row in profiles.items()}
        manifest = dispatch_service.build(
            store,
            int(args["plan"]),
            lane_id=int(lane) if lane else None,
            max_chars=int(budget) if isinstance(budget, int) else 0,
            context_windows=windows,
            context_percent=int(args.get("context_percent") or DEFAULT_TASK_CONTEXT_PERCENT),
        )
        manifest["profiles"] = profiles
        for item in manifest["dispatchable"]:
            item["profile"] = manifest["profiles"].get(item["role"], {})
        return manifest

    def _tool_task_brief(self, args: dict) -> object:
        store = self._need_store()
        task = store.get_task(int(args["id"]))
        if task is None:
            raise KeyError(f"task {args['id']} not found")
        windows = context_windows(store.db_path, host=str(args.get("host") or ""))
        window = int(args.get("context_window") or 0) or windows.get(
            task.role, DEFAULT_CONTEXT_WINDOW
        )
        percent = int(args.get("percent") or DEFAULT_TASK_CONTEXT_PERCENT)
        return task_brief.build(store, task.id, window, percent).to_dict()
