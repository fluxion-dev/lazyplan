"""Local MCP server: JSON-RPC 2.0 over stdio.

Stdlib only. Protocol frames go to stdout; diagnostics go to stderr. Tools and
resources reuse the same store/services as the CLI.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .. import audit, brief, lint, services, trace
from ..models import Milestone, Plan, Status, Task
from ..repo import find_repo_root, repo_label
from ..store import to_payload
from ..vcs import detect_backend
from .base import McpBase

PROTOCOL_VERSION = "2024-11-05"


def _id() -> dict:
    return {"type": "integer"}


def _str() -> dict:
    return {"type": "string"}


def _kind() -> dict:
    return {"type": "string", "enum": ["plan", "milestone", "task"]}


def _tool(
    name: str,
    description: str,
    properties: dict,
    required: list[str] | None = None,
    read_only: bool = True,
) -> dict:
    """Build one MCP tool definition."""
    return {
        "name": name,
        "description": description,
        "inputSchema": {
            "type": "object",
            "properties": properties,
            "required": required or [],
        },
        "annotations": {"readOnlyHint": read_only},
    }


def _tool_ok(payload: object) -> dict:
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(payload, indent=2, default=str),
            }
        ]
    }


def _tool_error(message: str) -> dict:
    return {
        "content": [{"type": "text", "text": message}],
        "isError": True,
    }


class ToolsMixin(McpBase):
    """MCP tool definitions and handlers."""

    def _write_registry(self) -> dict[str, tuple[dict, Any]]:
        """Write tools, omitted in read-only mode."""
        return {
            "create_plan": (
                _tool(
                    "create_plan",
                    "Create a plan.",
                    {"title": _str(), "why": _str(), "what": _str()},
                    ["title"],
                    False,
                ),
                self._tool_create_plan,
            ),
            "create_milestone": (
                _tool(
                    "create_milestone",
                    "Create a milestone.",
                    {"plan": _id(), "title": _str(), "desc": _str()},
                    ["plan", "title"],
                    False,
                ),
                self._tool_create_milestone,
            ),
            "create_task": (
                _tool(
                    "create_task",
                    "Create a task.",
                    {"milestone": _id(), "title": _str(), "desc": _str()},
                    ["milestone", "title"],
                    False,
                ),
                self._tool_create_task,
            ),
            "edit_row": (
                _tool(
                    "edit_row",
                    "Edit a plan, milestone, or task.",
                    {
                        "kind": _kind(),
                        "id": _id(),
                        "title": _str(),
                        "desc": _str(),
                        "why": _str(),
                    },
                    ["kind", "id"],
                    False,
                ),
                self._tool_edit,
            ),
            "move_row": (
                _tool(
                    "move_row",
                    "Move a row to todo, doing, or done.",
                    {
                        "kind": _kind(),
                        "id": _id(),
                        "to": {"type": "string", "enum": ["todo", "doing", "done"]},
                    },
                    ["kind", "id", "to"],
                    False,
                ),
                self._tool_move,
            ),
            "criterion_add": (
                _tool(
                    "criterion_add",
                    "Add an acceptance criterion.",
                    {"kind": _kind(), "id": _id(), "text": _str()},
                    ["kind", "id", "text"],
                    False,
                ),
                self._tool_criterion_add,
            ),
            "criterion_tick": (
                _tool("criterion_tick", "Tick a criterion.", {"id": _id()}, ["id"], False),
                self._tool_criterion_tick,
            ),
            "criterion_untick": (
                _tool("criterion_untick", "Untick a criterion.", {"id": _id()}, ["id"], False),
                self._tool_criterion_untick,
            ),
            "criterion_relate": (
                _tool(
                    "criterion_relate",
                    "Relate a criterion to a proving task.",
                    {"id": _id(), "task": _id()},
                    ["id", "task"],
                    False,
                ),
                self._tool_criterion_relate,
            ),
            "criterion_unrelate": (
                _tool(
                    "criterion_unrelate",
                    "Remove a criterion proof relation.",
                    {"id": _id(), "task": _id()},
                    ["id", "task"],
                    False,
                ),
                self._tool_criterion_unrelate,
            ),
            "claim_task": (
                _tool(
                    "claim_task",
                    "Claim a task lease.",
                    {"id": _id(), "ttl": _str(), "note": _str(), "force": {"type": "boolean"}},
                    ["id"],
                    False,
                ),
                self._tool_claim,
            ),
            "claim_renew": (
                _tool(
                    "claim_renew",
                    "Renew a task lease.",
                    {"id": _id(), "ttl": _str()},
                    ["id"],
                    False,
                ),
                self._tool_claim_renew,
            ),
            "claim_release": (
                _tool(
                    "claim_release",
                    "Release a task lease.",
                    {"id": _id(), "force": {"type": "boolean"}},
                    ["id"],
                    False,
                ),
                self._tool_claim_release,
            ),
            "note_add": (
                _tool(
                    "note_add",
                    "Add a handoff note.",
                    {"kind": _kind(), "id": _id(), "text": _str()},
                    ["kind", "id", "text"],
                    False,
                ),
                self._tool_note_add,
            ),
            "block_task": (
                _tool(
                    "block_task",
                    "Block a task with a reason.",
                    {"id": _id(), "reason": _str()},
                    ["id", "reason"],
                    False,
                ),
                self._tool_block,
            ),
            "unblock_task": (
                _tool("unblock_task", "Clear a task's blocked flag.", {"id": _id()}, ["id"], False),
                self._tool_unblock,
            ),
            "link_commit": (
                _tool(
                    "link_commit",
                    "Link a commit to a row.",
                    {"kind": _kind(), "id": _id(), "sha": _str(), "repo": _str()},
                    ["kind", "id"],
                    False,
                ),
                self._tool_link,
            ),
        }

    def _tool_trace(self, args: dict) -> object:
        store = self._need_store()
        if args.get("plan"):
            payload = trace.trace_plan(store, int(args["plan"]))
        elif args.get("criterion"):
            payload = trace.trace_criterion(store, int(args["criterion"]))
        else:
            raise ValueError("trace needs plan or criterion")
        if payload is None:
            raise KeyError("trace target not found")
        return payload

    def _tool_link(self, args: dict) -> object:
        store = self._need_store()
        kind = str(args["kind"])
        obj_id = int(args["id"])
        if store.get_parent(kind, obj_id) is None:
            raise KeyError(f"{kind} {obj_id} not found")
        target = str(args.get("repo") or ".")
        backend, root = detect_backend(target)
        if backend is None or root is None:
            raise ValueError("no VCS backend available")
        sha = str(args.get("sha") or "") or backend.head(root)
        if not sha:
            raise ValueError("no HEAD commit")
        info = backend.show(root, sha)
        if info is None:
            raise ValueError(f"unknown commit {sha}")
        link = store.link_commit(
            kind,
            obj_id,
            info.sha,
            subject=info.subject,
            author=info.author,
            timestamp=info.timestamp,
            repo_root=info.repo_root,
            files=info.files,
            actor=self.actor,
        )
        return vars(link)

    def _tool_list(self, args: dict) -> object:
        store = self._need_store()
        limit = args.get("limit")
        ids = [plan.id for plan in store.list_plans()]
        if isinstance(limit, int):
            ids = ids[: max(limit, 0)]
        return store.get_full_many("plan", ids)

    def _tool_criterion_untick(self, args: dict) -> object:
        criterion = self._need_store().set_criteria(int(args["id"]), False, actor=self.actor)
        if criterion is None:
            raise KeyError(f"criterion {args['id']} not found")
        return vars(criterion)

    def _tool_claim_release(self, args: dict) -> object:
        return services.release_task_claim(
            self._need_store(), int(args["id"]), self.actor, force=bool(args.get("force"))
        )

    def _tool_criterion_relate(self, args: dict) -> object:
        self._need_store().relate_criterion(int(args["id"]), int(args["task"]), actor=self.actor)
        return {"ok": True, "criterion": args["id"], "task": args["task"], "linked": True}

    def _tool_claims(self, args: dict) -> object:
        return self._need_store().list_claims(
            include_expired=bool(args.get("all")),
            plan_id=int(args["plan"]) if args.get("plan") else None,
        )

    def _read_registry(self) -> dict[str, tuple[dict, Any]]:
        """Read tools, always available."""
        return {
            "brief": (
                _tool(
                    "brief", "Session brief: active plan, doing task, next, gaps.", {"plan": _id()}
                ),
                self._tool_brief,
            ),
            "list_plans": (
                _tool(
                    "list_plans",
                    "All plans with milestones, tasks, and criteria.",
                    {"limit": {"type": "integer"}},
                ),
                self._tool_list,
            ),
            "show_row": (
                _tool(
                    "show_row",
                    "One plan, milestone, or task with full context.",
                    {"kind": _kind(), "id": _id()},
                    ["kind", "id"],
                ),
                self._tool_show,
            ),
            "claims": (
                _tool(
                    "claims",
                    "Active task leases, or all including expired.",
                    {"plan": _id(), "all": {"type": "boolean"}},
                ),
                self._tool_claims,
            ),
            "audit": (
                _tool(
                    "audit",
                    "Coverage, lag, gaps, and trace coverage.",
                    {"plan": _id(), "since": {"type": "string"}},
                ),
                self._tool_audit,
            ),
            "trace": (
                _tool(
                    "trace",
                    "Criterion to task, commit, and PR evidence.",
                    {"plan": _id(), "criterion": _id()},
                ),
                self._tool_trace,
            ),
            "lint": (
                _tool("lint", "Plan-quality findings for a plan.", {"plan": _id()}, ["plan"]),
                self._tool_lint,
            ),
            "info": (_tool("info", "Resolved database, scope, and counts.", {}), self._tool_info),
        }

    def _tool_claim_renew(self, args: dict) -> object:
        claim = services.renew_task_claim(
            self._need_store(), int(args["id"]), self.actor, ttl=args.get("ttl") or None
        )
        return vars(claim)

    def _tool_show(self, args: dict) -> object:
        store = self._need_store()
        kind = str(args["kind"])
        if kind not in ("plan", "milestone", "task"):
            raise ValueError("kind must be plan, milestone, or task")
        full = store.get_full(kind, int(args["id"]))
        if full is None:
            raise KeyError(f"{kind} {args['id']} not found")
        return full

    def _tool_unblock(self, args: dict) -> object:
        task = services.unblock_task(self._need_store(), int(args["id"]), actor=self.actor)
        return to_payload(vars(task))

    def _tool_lint(self, args: dict) -> object:
        findings = lint.lint_plan(self._need_store(), int(args["plan"]))
        if findings is None:
            raise KeyError(f"plan {args['plan']} not found")
        return [finding.to_dict() for finding in findings]

    def _tool_audit(self, args: dict) -> object:
        store = self._need_store()
        since = audit.parse_since(str(args["since"])) if args.get("since") else None
        report = audit.report(
            store,
            [int(args["plan"])] if args.get("plan") else None,
            since,
            Path.cwd(),
        )
        payload = report.to_dict()
        payload["breaches"] = audit.Thresholds().breaches(report)
        return payload

    def _tool_create_task(self, args: dict) -> object:
        task = services.create_task(
            self._need_store(),
            int(args["milestone"]),
            str(args["title"]),
            description=str(args.get("desc") or ""),
            actor=self.actor,
        )
        return to_payload(vars(task))

    def _tool_edit(self, args: dict) -> object:
        store = self._need_store()
        kind = str(args["kind"])
        obj_id = int(args["id"])
        title = str(args.get("title") or "") or None
        desc = str(args.get("desc") or "") or None
        updated: Plan | Milestone | Task | None
        if kind == "plan":
            updated = store.update_plan(
                obj_id,
                name=title,
                description=desc,
                goal=str(args.get("why") or "") or None,
                actor=self.actor,
            )
        elif kind == "milestone":
            updated = store.update_milestone(
                obj_id, title=title, description=desc, actor=self.actor
            )
        elif kind == "task":
            updated = store.update_task(obj_id, title=title, description=desc, actor=self.actor)
        else:
            raise ValueError("kind must be plan, milestone, or task")
        if updated is None:
            raise KeyError(f"{kind} {obj_id} not found")
        return to_payload(vars(updated))

    def _tool_info(self, args: dict) -> object:
        store = self._need_store()
        root = find_repo_root(Path.cwd())
        return {
            "db": str(store.path),
            "repo": str(root) if root else None,
            "scope": repo_label(store.path),
            "counts": store.counts(),
        }

    def _tool_claim(self, args: dict) -> object:
        return services.start_claim(
            self._need_store(),
            int(args["id"]),
            self.actor,
            ttl=args.get("ttl") or None,
            note=str(args.get("note") or ""),
            force=bool(args.get("force")),
        )

    def tools(self) -> list[dict]:
        """Tool definitions; write tools appear only outside read-only mode."""
        return [definition for definition, _handler in self._registry().values()]

    def _tool_move(self, args: dict) -> object:
        kind = str(args["kind"])
        obj_id = int(args["id"])
        ok = services.set_status(
            self._need_store(), kind, obj_id, Status(str(args["to"])), actor=self.actor
        )
        if not ok:
            raise KeyError(f"{kind} {obj_id} not found")
        return {"ok": True, "kind": kind, "id": obj_id, "to": args["to"]}

    def _tool_create_plan(self, args: dict) -> object:
        plan = services.create_plan(
            self._need_store(),
            str(args["title"]),
            str(args.get("what") or ""),
            goal=str(args.get("why") or ""),
            actor=self.actor,
        )
        return to_payload(vars(plan))

    def _tool_brief(self, args: dict) -> object:
        plan_id = args.get("plan")
        return brief.build(self._need_store(), plan_id)

    def _tool_criterion_tick(self, args: dict) -> object:
        criterion = self._need_store().set_criteria(int(args["id"]), True, actor=self.actor)
        if criterion is None:
            raise KeyError(f"criterion {args['id']} not found")
        return vars(criterion)

    def _tool_criterion_unrelate(self, args: dict) -> object:
        ok = self._need_store().unrelate_criterion(
            int(args["id"]), int(args["task"]), actor=self.actor
        )
        if not ok:
            raise ValueError("criterion is not linked to that task")
        return {"ok": True, "criterion": args["id"], "task": args["task"], "linked": False}

    def _tool_note_add(self, args: dict) -> object:
        return vars(
            self._need_store().add_note(
                str(args["kind"]), int(args["id"]), str(args["text"]), actor=self.actor
            )
        )

    def _tool_create_milestone(self, args: dict) -> object:
        milestone = services.create_milestone(
            self._need_store(),
            int(args["plan"]),
            str(args["title"]),
            str(args.get("desc") or ""),
            actor=self.actor,
        )
        return to_payload(vars(milestone))

    def _registry(self) -> dict[str, tuple[dict, Any]]:
        """Merge read and write tools for the current mode."""
        tools = self._read_registry()
        if not self.read_only:
            tools.update(self._write_registry())
        return tools

    def _tool_block(self, args: dict) -> object:
        task = services.block_task(
            self._need_store(), int(args["id"]), str(args["reason"]), actor=self.actor
        )
        return to_payload(vars(task))

    def _call_tool(self, request_id: object, params: dict) -> dict:
        name = params.get("name")
        if not isinstance(name, str):
            return self._error(request_id, -32602, "tool name is required")
        entry = self._registry().get(name)
        if entry is None:
            return self._error(request_id, -32601, f"tool not found: {name}")
        definition, handler = entry
        arguments = params.get("arguments") or {}
        if not isinstance(arguments, dict):
            return self._error(request_id, -32602, "arguments must be an object")
        missing = [
            key for key in definition["inputSchema"].get("required", []) if key not in arguments
        ]
        if missing:
            return self._error(request_id, -32602, f"missing arguments: {', '.join(missing)}")
        if self.read_only and definition.get("annotations", {}).get("readOnlyHint") is False:
            return self._result(request_id, _tool_error("read-only server"))
        try:
            payload = handler(arguments)
        except (KeyError, ValueError, RuntimeError) as exc:
            return self._result(request_id, _tool_error(str(exc)))
        return self._result(request_id, _tool_ok(payload))

    def _tool_criterion_add(self, args: dict) -> object:
        return vars(
            self._need_store().add_criteria(
                str(args["kind"]), int(args["id"]), str(args["text"]), actor=self.actor
            )
        )
