"""MCP evidence tools."""

from __future__ import annotations

from typing import Any

from lazyplan import services

from .base import McpBase
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
                    "Record proof for a criterion; tick only when it passes.",
                    {
                        "id": _id(),
                        "command": _str(),
                        "exit_code": {"type": "integer"},
                        "commit": _str(),
                        "pr": _str(),
                        "artifact": _str(),
                        "note": _str(),
                        "task": _id(),
                        "no_tick": {"type": "boolean"},
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
                self._tool_criterion_evidence,
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
            tick=not bool(args.get("no_tick")),
        )
        return {
            "evidence": vars(result.evidence),
            "criterion": vars(result.criterion),
            "ticked": result.ticked,
        }

    def _tool_criterion_evidence(self, args: dict) -> object:
        return [vars(row) for row in services.list_evidence(self._need_store(), int(args["id"]))]
