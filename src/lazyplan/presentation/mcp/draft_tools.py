"""MCP draft tools: review, annotate, revise, and promote plan drafts."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from lazyplan import services

from ...core.entities import DraftAnnotation, PlanDraft
from ...core.ports.app import AppPort
from .base import McpBase
from .draft_payloads import (
    annotation_payload,
    detail_payload,
    draft_payload,
    drafts_payload,
    promotion_payload,
)
from .schema import id_schema as _id
from .schema import str_schema as _str
from .schema import tool as _tool


class DraftToolsMixin(McpBase):
    """Draft review tools shared by CLI and MCP hosts."""

    def _draft_read_registry(self) -> list[tuple[dict, Any]]:
        """Read tools, always available."""
        return [
            (
                _tool(
                    "draft_list",
                    "Plan drafts with status and annotation counts.",
                    {
                        "status": {
                            "type": "string",
                            "enum": ["review", "revising", "promoted", "all"],
                        }
                    },
                ),
                self._tool_draft_list,
            ),
            (
                _tool(
                    "draft_show",
                    "One draft document with its blocks and annotations.",
                    {"id": _id()},
                    ["id"],
                ),
                self._tool_draft_show,
            ),
            (
                _tool(
                    "draft_annotations",
                    "Annotations on one draft by state.",
                    {
                        "id": _id(),
                        "status": {
                            "type": "string",
                            "enum": ["open", "addressed", "dismissed", "all"],
                        },
                    },
                    ["id"],
                ),
                self._tool_draft_annotations,
            ),
        ]

    def _draft_write_registry(self) -> list[tuple[dict, Any]]:
        """Write tools, omitted in read-only mode."""
        return [
            (
                _tool(
                    "draft_add",
                    "Store a validated plan document as a draft.",
                    {"document": {"type": "object"}},
                    ["document"],
                    False,
                ),
                self._tool_draft_add,
            ),
            (
                _tool(
                    "draft_revise",
                    "Replace a draft document with a revision of the base.",
                    {
                        "id": _id(),
                        "document": {"type": "object"},
                        "base_revision": {"type": "integer"},
                        "note": _str(),
                    },
                    ["id", "document", "base_revision"],
                    False,
                ),
                self._tool_draft_revise,
            ),
            (
                _tool(
                    "draft_ready",
                    "Return a clean revision to review.",
                    {"id": _id()},
                    ["id"],
                    False,
                ),
                self._tool_draft_ready,
            ),
            (
                _tool(
                    "draft_annotate",
                    "Annotate a draft block or selected quote.",
                    {
                        "id": _id(),
                        "block": _str(),
                        "kind": {
                            "type": "string",
                            "enum": ["comment", "question", "change"],
                        },
                        "text": _str(),
                        "quote": _str(),
                        "start": {"type": "integer"},
                        "end": {"type": "integer"},
                    },
                    ["id", "block", "kind", "text"],
                    False,
                ),
                self._tool_draft_annotate,
            ),
            (
                _tool(
                    "draft_respond",
                    "Answer one annotation and mark it addressed.",
                    {"id": _id(), "response": _str()},
                    ["id", "response"],
                    False,
                ),
                self._tool_draft_respond,
            ),
            (
                _tool(
                    "draft_resolve",
                    "Mark one annotation addressed, with an optional response.",
                    {"id": _id(), "response": _str()},
                    ["id"],
                    False,
                ),
                self._tool_draft_resolve,
            ),
            (
                _tool(
                    "draft_dismiss",
                    "Dismiss one annotation with a reason.",
                    {"id": _id(), "reason": _str()},
                    ["id"],
                    False,
                ),
                self._tool_draft_dismiss,
            ),
            (
                _tool(
                    "draft_promote",
                    "Create the plan tree from a clean draft.",
                    {"id": _id()},
                    ["id"],
                    False,
                ),
                self._tool_draft_promote,
            ),
            (
                _tool("draft_delete", "Delete a draft.", {"id": _id()}, ["id"], False),
                self._tool_draft_delete,
            ),
        ]

    @staticmethod
    def _draft_result(store: AppPort, draft: PlanDraft) -> dict:
        """One changed draft with its counts."""
        open_count, total_count = services.drafts.annotation_counts(store, draft.id)
        return {"draft": draft_payload(draft, open_count, total_count)}

    def _tool_draft_list(self, args: dict) -> object:
        return drafts_payload(self._need_store())

    def _tool_draft_show(self, args: dict) -> object:
        detail = services.drafts.detail(self._need_store(), int(args["id"]))
        return detail_payload(detail)

    def _tool_draft_annotations(self, args: dict) -> object:
        rows = services.drafts.list_annotations(
            self._need_store(), int(args["id"]), str(args.get("status") or "all")
        )
        return [annotation_payload(row) for row in rows]

    def _tool_draft_add(self, args: dict) -> object:
        store = self._need_store()
        draft = services.drafts.create(store, args.get("document"), actor=self.actor)
        return self._draft_result(store, draft)

    def _tool_draft_revise(self, args: dict) -> object:
        store = self._need_store()
        draft = services.drafts.revise(
            store,
            int(args["id"]),
            args.get("document"),
            int(args["base_revision"]),
            actor=self.actor,
            note=str(args.get("note") or ""),
        )
        return self._draft_result(store, draft)

    def _draft_transition(self, args: dict, run: Callable[..., PlanDraft]) -> object:
        """Run one draft state transition and return the changed draft."""
        store = self._need_store()
        draft = run(store, int(args["id"]), actor=self.actor)
        return self._draft_result(store, draft)

    def _tool_draft_ready(self, args: dict) -> object:
        return self._draft_transition(args, services.drafts.ready)

    def _tool_draft_annotate(self, args: dict) -> object:
        annotation = services.drafts.annotate(
            self._need_store(),
            int(args["id"]),
            str(args["block"]),
            str(args["kind"]),
            str(args["text"]),
            quote=str(args.get("quote") or ""),
            start_offset=int(args.get("start") or 0),
            end_offset=int(args.get("end") or 0),
            author=self.actor,
        )
        return {"annotation": annotation_payload(annotation)}

    def _tool_draft_respond(self, args: dict) -> object:
        annotation = services.drafts.respond(
            self._need_store(),
            int(args["id"]),
            str(args["response"]),
            actor=self.actor,
        )
        return {"annotation": annotation_payload(annotation)}

    def _annotation_transition(
        self, args: dict, run: Callable[..., DraftAnnotation], field: str
    ) -> object:
        """Run one annotation state change with a free-text field."""
        annotation = run(
            self._need_store(),
            int(args["id"]),
            str(args.get(field) or ""),
            actor=self.actor,
        )
        return {"annotation": annotation_payload(annotation)}

    def _tool_draft_resolve(self, args: dict) -> object:
        annotation = services.drafts.resolve(
            self._need_store(),
            int(args["id"]),
            str(args.get("response") or ""),
            actor=self.actor,
        )
        return {"annotation": annotation_payload(annotation)}

    def _tool_draft_dismiss(self, args: dict) -> object:
        return self._annotation_transition(args, services.drafts.dismiss, "reason")

    def _tool_draft_promote(self, args: dict) -> object:
        store = self._need_store()
        promotion = services.drafts.promote(store, int(args["id"]), actor=self.actor)
        open_count, total_count = services.drafts.annotation_counts(store, promotion.draft.id)
        return promotion_payload(promotion, open_count, total_count)

    def _tool_draft_delete(self, args: dict) -> object:
        store = self._need_store()
        removed = services.drafts.delete_draft(store, int(args["id"]), actor=self.actor)
        if not removed:
            raise KeyError(f"draft {args['id']} not found")
        return {"ok": True, "deleted": f"draft #{args['id']}"}
