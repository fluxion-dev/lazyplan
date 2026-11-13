"""MCP collaboration tools: criteria, comments, notes, sessions, refs, activity."""

from __future__ import annotations

from typing import Any

from lazyplan import services

from .base import McpBase
from .schema import id_schema as _id
from .schema import kind_schema as _kind
from .schema import str_schema as _str
from .schema import tool as _tool


class CollaborationToolsMixin(McpBase):
    """Criteria, comments, notes, sessions, references, and activity rows."""

    def _collaboration_write_registry(self) -> dict[str, tuple[dict, Any]]:
        return {
            "criterion_edit": (
                _tool(
                    "criterion_edit",
                    "Rewrite one criterion's text or completion.",
                    {
                        "id": _id(),
                        "text": _str(),
                        "done": {"type": "boolean"},
                        "reason": _str(),
                    },
                    ["id"],
                    False,
                ),
                self._tool_criterion_edit,
            ),
            "criterion_delete": (
                _tool(
                    "criterion_delete",
                    "Delete one criterion.",
                    {"id": _id(), "reason": _str()},
                    ["id"],
                    False,
                ),
                self._tool_criterion_delete,
            ),
            "delete_row": (
                _tool(
                    "delete_row",
                    "Delete a plan, milestone, or task.",
                    {"kind": _kind(), "id": _id(), "reason": _str()},
                    ["kind", "id"],
                    False,
                ),
                self._tool_delete_row,
            ),
            "comment_add": (
                _tool(
                    "comment_add",
                    "Add a review comment to a row.",
                    {"kind": _kind(), "id": _id(), "text": _str()},
                    ["kind", "id", "text"],
                    False,
                ),
                self._tool_comment_add,
            ),
            "comment_edit": (
                _tool(
                    "comment_edit",
                    "Rewrite one review comment.",
                    {"id": _id(), "text": _str()},
                    ["id", "text"],
                    False,
                ),
                self._tool_comment_edit,
            ),
            "comment_resolve": (
                _tool(
                    "comment_resolve",
                    "Resolve or unresolve a review comment.",
                    {"id": _id(), "resolved": {"type": "boolean"}},
                    ["id"],
                    False,
                ),
                self._tool_comment_resolve,
            ),
            "touch_add": (
                _tool(
                    "touch_add",
                    "Add a task touch-point path or glob.",
                    {"id": _id(), "path": _str()},
                    ["id", "path"],
                    False,
                ),
                self._tool_touch_add,
            ),
            "touch_remove": (
                _tool(
                    "touch_remove",
                    "Remove a task touch-point path or glob.",
                    {"id": _id(), "path": _str()},
                    ["id", "path"],
                    False,
                ),
                self._tool_touch_remove,
            ),
            "reference_link": (
                _tool(
                    "reference_link",
                    "Attach an external URL to a plan.",
                    {"plan": _id(), "url": _str(), "kind": _str(), "title": _str()},
                    ["plan", "url"],
                    False,
                ),
                self._tool_reference_link,
            ),
            "reference_unlink": (
                _tool(
                    "reference_unlink",
                    "Remove one external reference from a plan.",
                    {"plan": _id(), "ref": _id(), "url": _str()},
                    ["plan"],
                    False,
                ),
                self._tool_reference_unlink,
            ),
        }

    def _collaboration_read_registry(self) -> dict[str, tuple[dict, Any]]:
        return {
            "criterion_list": (
                _tool(
                    "criterion_list",
                    "Criteria on one plan, milestone, or task.",
                    {"kind": _kind(), "id": _id()},
                    ["kind", "id"],
                ),
                self._tool_criterion_list,
            ),
            "comment_list": (
                _tool(
                    "comment_list",
                    "Comments on one row, optionally by mention.",
                    {"kind": _kind(), "id": _id(), "mentions": _str()},
                    ["kind", "id"],
                ),
                self._tool_comment_list,
            ),
            "note_list": (
                _tool(
                    "note_list",
                    "Notes on one row.",
                    {"kind": _kind(), "id": _id(), "limit": _id()},
                    ["kind", "id"],
                ),
                self._tool_note_list,
            ),
            "agent_list": (
                _tool(
                    "agent_list",
                    "Live agents, newest first.",
                    {"plan": _id(), "limit": _id(), "live": {"type": "boolean"}},
                ),
                self._tool_agent_list,
            ),
            "session_list": (
                _tool(
                    "session_list",
                    "Legacy session history, newest first.",
                    {"plan": _id(), "limit": _id()},
                ),
                self._tool_session_list,
            ),
            "reference_list": (
                _tool(
                    "reference_list",
                    "External references on one plan.",
                    {"plan": _id()},
                    ["plan"],
                ),
                self._tool_reference_list,
            ),
            "touch_list": (
                _tool(
                    "touch_list",
                    "Touch-point paths on one task.",
                    {"task": _id()},
                    ["task"],
                ),
                self._tool_touch_list,
            ),
            "activity_list": (
                _tool(
                    "activity_list",
                    "Recent events.",
                    {
                        "limit": _id(),
                        "actor": _str(),
                        "kind": _str(),
                    },
                ),
                self._tool_activity_list,
            ),
        }

    def _tool_criterion_edit(self, args: dict) -> object:
        text = args.get("text")
        done = args.get("done")
        row = self._need_store().update_criterion(
            int(args["id"]),
            text=None if text is None else str(text),
            done=None if done is None else bool(done),
            actor=self.actor,
            reason=str(args.get("reason") or ""),
        )
        if row is None:
            raise KeyError(f"criterion {args['id']} not found")
        return vars(row)

    def _tool_criterion_delete(self, args: dict) -> object:
        ok = self._need_store().delete_criteria(
            int(args["id"]), actor=self.actor, reason=str(args.get("reason") or "")
        )
        if not ok:
            raise KeyError(f"criterion {args['id']} not found")
        return {"ok": True, "deleted": args["id"]}

    def _tool_delete_row(self, args: dict) -> object:
        ok = services.delete_row(
            self._need_store(),
            str(args["kind"]),
            int(args["id"]),
            actor=self.actor,
            reason=str(args.get("reason") or ""),
        )
        if not ok:
            raise KeyError(f"{args['kind']} {args['id']} not found")
        return {"ok": True, "deleted": f"{args['kind']} {args['id']}"}

    def _tool_comment_add(self, args: dict) -> object:
        comment = services.add_comment(
            self._need_store(),
            str(args["kind"]),
            int(args["id"]),
            str(args["text"]),
            actor=self.actor,
        )
        return vars(comment)

    def _tool_comment_edit(self, args: dict) -> object:
        comment = self._need_store().update_comment(
            int(args["id"]), str(args["text"]), actor=self.actor
        )
        if comment is None:
            raise KeyError(f"comment {args['id']} not found")
        return vars(comment)

    def _tool_comment_resolve(self, args: dict) -> object:
        comment = self._need_store().resolve_comment(
            int(args["id"]),
            resolved=bool(args.get("resolved", True)),
            actor=self.actor,
        )
        if comment is None:
            raise KeyError(f"comment {args['id']} not found")
        return vars(comment)

    def _tool_touch_add(self, args: dict) -> object:
        path = self._need_store().add_touchpoint(
            int(args["id"]), str(args["path"]), actor=self.actor
        )
        return {"ok": True, "task": args["id"], "path": path}

    def _tool_touch_remove(self, args: dict) -> object:
        ok = self._need_store().remove_touchpoint(
            int(args["id"]), str(args["path"]), actor=self.actor
        )
        return {"ok": ok, "task": args["id"], "path": args["path"]}

    def _tool_reference_link(self, args: dict) -> object:
        return vars(
            services.link_ref(
                self._need_store(),
                int(args["plan"]),
                str(args["url"]),
                kind=str(args.get("kind") or "issue"),
                title=str(args.get("title") or ""),
                actor=self.actor,
            )
        )

    def _tool_reference_unlink(self, args: dict) -> object:
        ok = services.unlink_ref(
            self._need_store(),
            int(args["plan"]),
            ref_id=int(args["ref"]) if args.get("ref") else 0,
            url=str(args.get("url") or ""),
            actor=self.actor,
        )
        return {"ok": ok, "plan": args["plan"]}

    def _tool_criterion_list(self, args: dict) -> object:
        return [
            vars(row)
            for row in self._need_store().list_criteria(str(args["kind"]), int(args["id"]))
        ]

    def _tool_comment_list(self, args: dict) -> object:
        return [
            vars(row)
            for row in services.list_comments(
                self._need_store(),
                str(args["kind"]),
                int(args["id"]),
                mentions=str(args["mentions"]) if args.get("mentions") else None,
            )
        ]

    def _tool_note_list(self, args: dict) -> object:
        limit = int(args["limit"]) if args.get("limit") else None
        return [
            vars(row)
            for row in services.list_notes(
                self._need_store(), str(args["kind"]), int(args["id"]), limit=limit
            )
        ]

    def _tool_agent_list(self, args: dict) -> object:
        store = self._need_store()
        return [
            vars(row)
            for row in store.list_agents(
                plan_id=int(args["plan"]) if args.get("plan") else None,
                live_only=bool(args.get("live")),
                limit=int(args["limit"]) if args.get("limit") else 20,
            )
        ]

    def _tool_session_list(self, args: dict) -> object:
        return [
            vars(row)
            for row in self._need_store().list_sessions(
                plan_id=int(args["plan"]) if args.get("plan") else None,
                limit=int(args["limit"]) if args.get("limit") else 20,
            )
        ]

    def _tool_reference_list(self, args: dict) -> object:
        return [vars(row) for row in services.list_refs(self._need_store(), int(args["plan"]))]

    def _tool_touch_list(self, args: dict) -> object:
        return self._need_store().list_touchpoints(int(args["task"]))

    def _tool_activity_list(self, args: dict) -> object:
        store = self._need_store()
        limit = int(args["limit"]) if args.get("limit") else 50
        rows = store.feed(limit)
        actor = str(args.get("actor") or "")
        kind = str(args.get("kind") or "")
        if actor:
            rows = [row for row in rows if str(row.get("actor")) == actor]
        if kind:
            rows = [row for row in rows if str(row.get("kind")) == kind]
        return rows


__all__ = ["CollaborationToolsMixin"]
