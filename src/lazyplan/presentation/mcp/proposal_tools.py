"""MCP tools that stage structural changes for human review."""

from __future__ import annotations

from typing import Any

from lazyplan.services import plan_document

from .base import McpBase
from .schema import id_schema as _id
from .schema import kind_schema as _kind
from .schema import str_schema as _str
from .schema import tool as _tool


class ProposalToolsMixin(McpBase):
    """Write tools that never mutate plan rows."""

    def _proposal_write_registry(self) -> dict[str, tuple[dict, Any]]:
        return {
            "propose_plan": (
                _tool(
                    "propose_plan",
                    "Stage a plan document for human review; does not create rows.",
                    {
                        "title": _str(),
                        "summary": _str(),
                        "document": {"type": "object"},
                    },
                    ["title", "document"],
                    False,
                ),
                self._tool_propose_plan,
            ),
            "propose_edit": (
                _tool(
                    "propose_edit",
                    "Stage an edit to a plan, milestone, or task for review.",
                    {
                        "kind": _kind(),
                        "id": _id(),
                        "title": _str(),
                        "desc": _str(),
                        "why": _str(),
                        "reason": _str(),
                        "summary": _str(),
                    },
                    ["kind", "id"],
                    False,
                ),
                self._tool_propose_edit,
            ),
            "propose_task": (
                _tool(
                    "propose_task",
                    "Stage a new task under a milestone for review.",
                    {
                        "milestone": _id(),
                        "title": _str(),
                        "desc": _str(),
                        "summary": _str(),
                    },
                    ["milestone", "title"],
                    False,
                ),
                self._tool_propose_task,
            ),
        }

    def _proposal_read_registry(self) -> dict[str, tuple[dict, Any]]:
        return {
            "proposal_list": (
                _tool(
                    "proposal_list",
                    "Pending or resolved agent proposals.",
                    {
                        "status": {
                            "type": "string",
                            "enum": ["pending", "applied", "rejected", "all"],
                        },
                        "limit": {"type": "integer"},
                    },
                    [],
                ),
                self._tool_proposal_list,
            )
        }

    def _tool_propose_plan(self, args: dict) -> object:
        store = self._need_store()
        document = args.get("document")
        if not isinstance(document, dict):
            raise ValueError("document must be an object")
        plan_document.validate_document(store, document)
        proposal = store.add_proposal(
            "plan_document",
            str(args["title"]),
            {"document": document},
            summary=str(args.get("summary") or ""),
            actor=self.actor,
        )
        return {"proposal": proposal}

    def _tool_propose_edit(self, args: dict) -> object:
        store = self._need_store()
        kind = str(args["kind"])
        row_id = int(args["id"])
        if store.get_full(kind, row_id) is None:
            raise KeyError(f"{kind} {row_id} not found")
        proposal = store.add_proposal(
            "row_edit",
            f"Edit {kind} #{row_id}",
            {
                "kind": kind,
                "id": row_id,
                "title": str(args.get("title") or ""),
                "desc": str(args.get("desc") or ""),
                "why": str(args.get("why") or ""),
                "reason": str(args.get("reason") or ""),
            },
            summary=str(args.get("summary") or ""),
            actor=self.actor,
        )
        return {"proposal": proposal}

    def _tool_propose_task(self, args: dict) -> object:
        store = self._need_store()
        milestone_id = int(args["milestone"])
        if store.get_milestone(milestone_id) is None:
            raise KeyError(f"milestone {milestone_id} not found")
        proposal = store.add_proposal(
            "task_create",
            str(args["title"]),
            {
                "milestone": milestone_id,
                "title": str(args["title"]),
                "desc": str(args.get("desc") or ""),
            },
            summary=str(args.get("summary") or ""),
            actor=self.actor,
        )
        return {"proposal": proposal}

    def _tool_proposal_list(self, args: dict) -> object:
        return self._need_store().list_proposals(
            str(args.get("status") or "pending"),
            limit=int(args.get("limit") or 20),
        )
