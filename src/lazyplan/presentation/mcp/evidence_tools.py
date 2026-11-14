"""MCP evidence tools."""

from __future__ import annotations

from typing import Any

from lazyplan import services

from .base import McpBase
from .handlers import id_rows
from .schema import id_schema as _id
from .schema import str_schema as _str
from .schema import tool as _tool


class EvidenceToolsMixin(McpBase):
    """Criterion proof tools."""

    def _evidence_write_registry(self) -> dict[str, tuple[dict, Any]]:
        """Write tools, omitted in read-only mode."""
        return {
            "criterion_prove": (
                _tool(
                    "criterion_prove",
                    "Record proof for a criterion.",
                    {
                        "id": _id(),
                        "command": _str(),
                        "exit_code": {"type": "integer"},
                        "commit": _str(),
                        "pr": _str(),
                        "artifact": _str(),
                        "note": _str(),
                        "task": _id(),
                    },
                    ["id"],
                    False,
                ),
                self._tool_criterion_prove,
            )
        }

    def _evidence_read_registry(self) -> dict[str, tuple[dict, Any]]:
        """Read tools, always available."""
        return {
            "criterion_evidence": (
                _tool(
                    "criterion_evidence",
                    "Proof rows for one criterion.",
                    {"id": _id()},
                    ["id"],
                ),
                id_rows(
                    self._need_store,
                    lambda store, criterion_id: services.list_evidence(store, criterion_id),
                ),
            )
        }

    def _tool_criterion_prove(self, args: dict) -> object:
        task_id = int(args["task"]) if args.get("task") else None
        result = services.prove(
            self._need_store(),
            int(args["id"]),
            command=str(args.get("command") or ""),
            exit_code=args.get("exit_code"),
            commit_sha=str(args.get("commit") or ""),
            pr_url=str(args.get("pr") or ""),
            artifact_path=str(args.get("artifact") or ""),
            note=str(args.get("note") or ""),
            task_id=task_id,
            actor=self.actor,
        )
        return {
            "evidence": vars(result.evidence),
            "criterion": vars(result.criterion),
        }
