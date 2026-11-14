"""MCP question and readiness tools."""

from __future__ import annotations

from typing import Any

from lazyplan import services

from .base import McpBase
from .handlers import question_note
from .schema import id_schema as _id
from .schema import str_schema as _str
from .schema import tool as _tool


class QuestionToolsMixin(McpBase):
    """Plan questions and the readiness gate."""

    def _question_write_registry(self) -> list[tuple[dict, Any]]:
        """Write tools, omitted in read-only mode."""
        return [
            (
                _tool(
                    "question_add",
                    "Add an open question to a plan.",
                    {"plan": _id(), "text": _str()},
                    ["plan", "text"],
                    False,
                ),
                self._tool_question_add,
            ),
            (
                _tool(
                    "question_resolve",
                    "Resolve a question with an answer.",
                    {"id": _id(), "note": _str()},
                    ["id"],
                    False,
                ),
                question_note(self._need_store, self.actor, services.resolve_question),
            ),
            (
                _tool(
                    "question_reopen",
                    "Reopen a question and record why.",
                    {"id": _id(), "note": _str()},
                    ["id"],
                    False,
                ),
                question_note(self._need_store, self.actor, services.reopen_question),
            ),
        ]

    def _question_read_registry(self) -> list[tuple[dict, Any]]:
        """Read tools, always available."""
        return [
            (
                _tool(
                    "question_list",
                    "Questions on one plan by state.",
                    {
                        "plan": _id(),
                        "status": {"type": "string", "enum": ["open", "resolved", "all"]},
                    },
                    ["plan"],
                ),
                self._tool_question_list,
            ),
            (
                _tool(
                    "plan_ready",
                    "Lint, coverage, and open-question readiness for a plan.",
                    {"id": _id()},
                    ["id"],
                ),
                self._tool_plan_ready,
            ),
        ]

    def _tool_question_add(self, args: dict) -> object:
        question = services.add_question(
            self._need_store(),
            int(args["plan"]),
            str(args["text"]),
            actor=self.actor,
        )
        return vars(question)

    def _tool_question_list(self, args: dict) -> object:
        rows = services.list_questions(
            self._need_store(),
            int(args["plan"]),
            str(args.get("status") or "open"),
        )
        return [vars(row) for row in rows]

    def _tool_plan_ready(self, args: dict) -> object:
        result = services.plan_ready(self._need_store(), int(args["id"]))
        if result is None:
            raise KeyError(f"plan {args['id']} not found")
        return result.to_dict()
