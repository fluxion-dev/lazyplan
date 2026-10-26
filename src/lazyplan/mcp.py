"""Local MCP server: JSON-RPC 2.0 over stdio.

Stdlib only. Protocol frames go to stdout; diagnostics go to stderr. Tools and
resources reuse the same store/services as the CLI.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, TextIO

from . import audit, brief, lint, services, trace
from .models import Milestone, Plan, Status, Task
from .repo import find_repo_root, repo_label
from .store import Store, _ser
from .vcs import detect_backend

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


class McpServer:
    """One local MCP session bound to one database and actor."""

    def __init__(
        self,
        store: Store | None,
        actor: str = "human",
        read_only: bool = False,
        db_path: str = "",
    ) -> None:
        self.store = store
        self.actor = actor
        self.read_only = read_only
        self.db_path = db_path

    # -- protocol -----------------------------------------------------
    @staticmethod
    def _error(request_id: object, code: int, message: str) -> dict:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": code, "message": message},
        }

    def _result(self, request_id: object, result: object) -> dict:
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    def handle(self, request: object) -> dict | None:
        """Handle one decoded request; None for notifications."""
        if not isinstance(request, dict):
            return self._error(None, -32600, "invalid request")
        request_id = request.get("id")
        method = request.get("method")
        if not isinstance(method, str):
            return self._error(request_id, -32600, "missing method")
        params = request.get("params")
        if params is None:
            params = {}
        if not isinstance(params, dict):
            return self._error(request_id, -32602, "params must be an object")
        if request_id is None:
            return None
        if method == "initialize":
            return self._result(
                request_id,
                {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {
                        "tools": {"listChanged": False},
                        "resources": {"listChanged": False, "subscribe": False},
                    },
                    "serverInfo": {"name": "lazyplan", "version": "0"},
                },
            )
        if method == "ping":
            return self._result(request_id, {})
        if method == "tools/list":
            return self._result(request_id, {"tools": self.tools()})
        if method == "tools/call":
            return self._call_tool(request_id, params)
        if method == "resources/list":
            return self._result(request_id, {"resources": self.resources()})
        if method == "resources/read":
            return self._read_resource(request_id, params)
        return self._error(request_id, -32601, f"method not found: {method}")

    # -- protocol surface --------------------------------------------
    def tools(self) -> list[dict]:
        """Tool definitions; write tools appear only outside read-only mode."""
        return [definition for definition, _handler in self._registry().values()]

    def _registry(self) -> dict[str, tuple[dict, Any]]:
        """Name -> (definition, handler); reads first, writes outside read-only."""
        tools: dict[str, tuple[dict, Any]] = {
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
        if self.read_only:
            return tools
        tools.update(
            {
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
                    _tool(
                        "unblock_task", "Clear a task's blocked flag.", {"id": _id()}, ["id"], False
                    ),
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
        )
        return tools

    def resources(self) -> list[dict]:
        """Resource definitions."""
        return [
            {
                "uri": "lazyplan://brief",
                "name": "Session brief",
                "mimeType": "application/json",
            },
            {
                "uri": "lazyplan://plan/1",
                "name": "Plan document",
                "mimeType": "application/json",
            },
        ]

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

    def _need_store(self) -> Store:
        if self.store is None:
            raise RuntimeError("no database")
        return self.store

    def _tool_brief(self, args: dict) -> object:
        plan_id = args.get("plan")
        return brief.build(self._need_store(), plan_id)

    def _tool_list(self, args: dict) -> object:
        store = self._need_store()
        limit = args.get("limit")
        plans = []
        for plan in store.list_plans():
            full = store.get_full("plan", plan.id)
            if full is not None:
                plans.append(full)
            if isinstance(limit, int) and len(plans) >= limit:
                break
        return plans

    def _tool_show(self, args: dict) -> object:
        store = self._need_store()
        kind = str(args["kind"])
        if kind not in ("plan", "milestone", "task"):
            raise ValueError("kind must be plan, milestone, or task")
        full = store.get_full(kind, int(args["id"]))
        if full is None:
            raise KeyError(f"{kind} {args['id']} not found")
        return full

    def _tool_claims(self, args: dict) -> object:
        return self._need_store().list_claims(
            include_expired=bool(args.get("all")),
            plan_id=int(args["plan"]) if args.get("plan") else None,
        )

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

    def _tool_lint(self, args: dict) -> object:
        findings = lint.lint_plan(self._need_store(), int(args["plan"]))
        if findings is None:
            raise KeyError(f"plan {args['plan']} not found")
        return [finding.to_dict() for finding in findings]

    def _tool_info(self, args: dict) -> object:
        store = self._need_store()
        root = find_repo_root(Path.cwd())
        return {
            "db": str(store.path),
            "repo": str(root) if root else None,
            "scope": repo_label(store.path),
            "counts": store.counts(),
        }

    def _tool_create_plan(self, args: dict) -> object:
        plan = services.create_plan(
            self._need_store(),
            str(args["title"]),
            str(args.get("what") or ""),
            goal=str(args.get("why") or ""),
            actor=self.actor,
        )
        return _ser(vars(plan))

    def _tool_create_milestone(self, args: dict) -> object:
        milestone = services.create_milestone(
            self._need_store(),
            int(args["plan"]),
            str(args["title"]),
            str(args.get("desc") or ""),
            actor=self.actor,
        )
        return _ser(vars(milestone))

    def _tool_create_task(self, args: dict) -> object:
        task = services.create_task(
            self._need_store(),
            int(args["milestone"]),
            str(args["title"]),
            description=str(args.get("desc") or ""),
            actor=self.actor,
        )
        return _ser(vars(task))

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
        return _ser(vars(updated))

    def _tool_move(self, args: dict) -> object:
        kind = str(args["kind"])
        obj_id = int(args["id"])
        ok = services.set_status(
            self._need_store(), kind, obj_id, Status(str(args["to"])), actor=self.actor
        )
        if not ok:
            raise KeyError(f"{kind} {obj_id} not found")
        return {"ok": True, "kind": kind, "id": obj_id, "to": args["to"]}

    def _tool_criterion_add(self, args: dict) -> object:
        return vars(
            self._need_store().add_criteria(
                str(args["kind"]), int(args["id"]), str(args["text"]), actor=self.actor
            )
        )

    def _tool_criterion_tick(self, args: dict) -> object:
        criterion = self._need_store().set_criteria(int(args["id"]), True, actor=self.actor)
        if criterion is None:
            raise KeyError(f"criterion {args['id']} not found")
        return vars(criterion)

    def _tool_criterion_untick(self, args: dict) -> object:
        criterion = self._need_store().set_criteria(int(args["id"]), False, actor=self.actor)
        if criterion is None:
            raise KeyError(f"criterion {args['id']} not found")
        return vars(criterion)

    def _tool_criterion_relate(self, args: dict) -> object:
        self._need_store().relate_criterion(int(args["id"]), int(args["task"]), actor=self.actor)
        return {"ok": True, "criterion": args["id"], "task": args["task"], "linked": True}

    def _tool_criterion_unrelate(self, args: dict) -> object:
        ok = self._need_store().unrelate_criterion(
            int(args["id"]), int(args["task"]), actor=self.actor
        )
        if not ok:
            raise ValueError("criterion is not linked to that task")
        return {"ok": True, "criterion": args["id"], "task": args["task"], "linked": False}

    def _tool_claim(self, args: dict) -> object:
        return services.start_claim(
            self._need_store(),
            int(args["id"]),
            self.actor,
            ttl=args.get("ttl") or None,
            note=str(args.get("note") or ""),
            force=bool(args.get("force")),
        )

    def _tool_claim_renew(self, args: dict) -> object:
        claim = services.renew_task_claim(
            self._need_store(), int(args["id"]), self.actor, ttl=args.get("ttl") or None
        )
        return vars(claim)

    def _tool_claim_release(self, args: dict) -> object:
        return services.release_task_claim(
            self._need_store(), int(args["id"]), self.actor, force=bool(args.get("force"))
        )

    def _tool_note_add(self, args: dict) -> object:
        return vars(
            self._need_store().add_note(
                str(args["kind"]), int(args["id"]), str(args["text"]), actor=self.actor
            )
        )

    def _tool_block(self, args: dict) -> object:
        task = services.block_task(
            self._need_store(), int(args["id"]), str(args["reason"]), actor=self.actor
        )
        return _ser(vars(task))

    def _tool_unblock(self, args: dict) -> object:
        task = services.unblock_task(self._need_store(), int(args["id"]), actor=self.actor)
        return _ser(vars(task))

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

    def _read_resource(self, request_id: object, params: dict) -> dict:
        uri = params.get("uri")
        if not isinstance(uri, str):
            return self._error(request_id, -32602, "resource uri is required")
        try:
            store = self._need_store()
            if uri == "lazyplan://brief":
                payload: object = brief.build(store)
            elif uri.startswith("lazyplan://plan/"):
                plan_id = int(uri.rsplit("/", 1)[-1])
                payload = store.get_full("plan", plan_id)
                if payload is None:
                    raise KeyError(f"plan {plan_id} not found")
            else:
                return self._error(request_id, -32002, f"resource not found: {uri}")
        except (KeyError, ValueError, RuntimeError) as exc:
            return self._error(request_id, -32002, str(exc))
        return self._result(
            request_id,
            {
                "contents": [
                    {
                        "uri": uri,
                        "mimeType": "application/json",
                        "text": json.dumps(payload, indent=2, default=str),
                    }
                ]
            },
        )

    # -- loop ---------------------------------------------------------
    def serve(self, stdin: TextIO | None = None, stdout: TextIO | None = None) -> int:
        """Read JSON-RPC frames until EOF; never crash the loop."""
        source = stdin or sys.stdin
        sink = stdout or sys.stdout
        for line in source:
            line = line.strip()
            if not line:
                continue
            response: dict | None
            try:
                request = json.loads(line)
            except ValueError:
                response = self._error(None, -32700, "parse error")
            else:
                try:
                    response = self.handle(request)
                except Exception as exc:  # keep the session alive
                    response = self._error(
                        request.get("id") if isinstance(request, dict) else None,
                        -32603,
                        f"internal error: {exc}",
                    )
            if response is None:
                continue
            sink.write(json.dumps(response, separators=(",", ":"), default=str) + "\n")
            sink.flush()
        return 0


def build_server(db_path: str, actor: str = "human", read_only: bool = False) -> McpServer:
    """Open or skip the database according to the mode."""
    path = Path(db_path).expanduser()
    if read_only and not path.is_file():
        return McpServer(None, actor=actor, read_only=True, db_path=str(path))
    return McpServer(Store(str(path)), actor=actor, read_only=read_only, db_path=str(path))


def run(db_path: str, actor: str, read_only: bool = False) -> int:
    """Entry point used by the CLI."""
    return build_server(db_path, actor=actor, read_only=read_only).serve()
