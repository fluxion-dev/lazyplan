"""MCP review tool."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from lazyplan import services

from .base import McpBase
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
                self._tool_review,
            ),
            "ship": (
                _tool(
                    "ship",
                    "Deterministic Markdown outcome ship note for one plan.",
                    {"plan": _id(), "max_chars": {"type": "integer"}},
                ),
                self._tool_ship,
            ),
        }

    def _tool_review(self, args: dict) -> object:
        store = self._need_store()
        plan = (
            store.get_plan(int(args["plan"])) if args.get("plan") else services.active_plan(store)
        )
        if plan is None:
            return {"plan": None, "markdown": "no active plans\n", "payload": {}}
        packet = services.build_review(
            store,
            plan.id,
            max_chars=int(args.get("max_chars") or 0),
            cwd=Path.cwd(),
        )
        if packet is None:
            raise KeyError(f"plan {plan.id} not found")
        return {
            "plan": plan.id,
            "markdown": packet.markdown,
            "payload": packet.payload,
        }

    def _tool_ship(self, args: dict) -> object:
        store = self._need_store()
        plan = (
            store.get_plan(int(args["plan"])) if args.get("plan") else services.active_plan(store)
        )
        if plan is None:
            return {"plan": None, "markdown": "no active plans\n", "payload": {}}
        note = services.build_ship(
            store,
            plan.id,
            max_chars=int(args.get("max_chars") or 0),
            cwd=Path.cwd(),
        )
        if note is None:
            raise KeyError(f"plan {plan.id} not found")
        return {
            "plan": plan.id,
            "markdown": note.markdown,
            "payload": note.payload,
        }
