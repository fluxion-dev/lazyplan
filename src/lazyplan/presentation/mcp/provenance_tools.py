"""MCP provenance tools: commits, repos, pull requests, git, source, approval."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from lazyplan import services
from lazyplan.infrastructure.forge import parse_pull_url
from lazyplan.services.source import build_source_trail

from .base import McpBase
from .schema import id_schema as _id
from .schema import kind_schema as _kind
from .schema import str_schema as _str
from .schema import tool as _tool


class ProvenanceToolsMixin(McpBase):
    """Read-only provenance plus the few explicit write actions."""

    def _provenance_write_registry(self) -> dict[str, tuple[dict, Any]]:
        return {
            "finish_task": (
                _tool(
                    "finish_task",
                    "Link branch commits and finish a task through the gates.",
                    {
                        "id": _id(),
                        "repo": _str(),
                        "require_pr": {"type": "boolean"},
                        "require_checks": {"type": "boolean"},
                        "require_evidence": {"type": "boolean"},
                        "override": _str(),
                    },
                    ["id"],
                    False,
                ),
                self._tool_finish_task,
            ),
            "commit_refresh": (
                _tool(
                    "commit_refresh",
                    "Re-resolve cached commit links and mark stale rows.",
                    {"kind": _kind(), "id": _id()},
                    ["kind", "id"],
                    False,
                ),
                self._tool_commit_refresh,
            ),
            "plan_approve": (
                _tool(
                    "plan_approve",
                    "Approve the current plan scope.",
                    {
                        "id": _id(),
                        "reason": _str(),
                        "enforce": {"type": "boolean"},
                    },
                    ["id"],
                    False,
                ),
                self._tool_plan_approve,
            ),
            "pull_request_refresh": (
                _tool(
                    "pull_request_refresh",
                    "Refresh cached pull requests from GitHub (network).",
                    {"kind": _kind(), "id": _id()},
                    ["kind", "id"],
                    False,
                ),
                self._tool_pull_request_refresh,
            ),
            "pull_request_link": (
                _tool(
                    "pull_request_link",
                    "Attach a GitHub pull request URL to a row.",
                    {"kind": _kind(), "id": _id(), "url": _str(), "title": _str(), "state": _str()},
                    ["kind", "id", "url"],
                    False,
                ),
                self._tool_pull_request_link,
            ),
            "pull_request_unlink": (
                _tool(
                    "pull_request_unlink",
                    "Detach one cached pull request.",
                    {"kind": _kind(), "id": _id(), "number": _id()},
                    ["kind", "id", "number"],
                    False,
                ),
                self._tool_pull_request_unlink,
            ),
        }

    def _provenance_read_registry(self) -> dict[str, tuple[dict, Any]]:
        return {
            "git_status": (
                _tool(
                    "git_status",
                    "Branch and dirty state for a row's linked checkouts.",
                    {"kind": _kind(), "id": _id()},
                    ["kind", "id"],
                ),
                self._tool_git_status,
            ),
            "source_trail": (
                _tool(
                    "source_trail",
                    "Repos, commits, files, and pull requests for a row.",
                    {"kind": _kind(), "id": _id()},
                    ["kind", "id"],
                ),
                self._tool_source_trail,
            ),
            "commit_list": (
                _tool(
                    "commit_list",
                    "Commits linked to a row.",
                    {"kind": _kind(), "id": _id()},
                    ["kind", "id"],
                ),
                self._tool_commit_list,
            ),
            "repo_list": (
                _tool(
                    "repo_list",
                    "Repositories linked to a row.",
                    {"kind": _kind(), "id": _id(), "effective": {"type": "boolean"}},
                    ["kind", "id"],
                ),
                self._tool_repo_list,
            ),
            "pull_request_list": (
                _tool(
                    "pull_request_list",
                    "Cached pull requests linked to a row.",
                    {"kind": _kind(), "id": _id()},
                    ["kind", "id"],
                ),
                self._tool_pull_request_list,
            ),
            "plan_diff": (
                _tool(
                    "plan_diff",
                    "Scope drift since a plan approval.",
                    {"id": _id(), "from_revision": _id(), "to_revision": _id()},
                    ["id"],
                ),
                self._tool_plan_diff,
            ),
            "export_plan": (
                _tool(
                    "export_plan",
                    "Markdown export of one plan.",
                    {"id": _id()},
                    ["id"],
                ),
                self._tool_export_plan,
            ),
        }

    def _tool_finish_task(self, args: dict) -> object:
        return services.finish_task(
            self._need_store(),
            int(args["id"]),
            repo_path=str(args.get("repo") or ""),
            actor=self.actor,
            require_pr=bool(args.get("require_pr")),
            require_checks=bool(args.get("require_checks")),
            require_evidence=bool(args.get("require_evidence")),
            override=str(args.get("override") or ""),
        )

    def _tool_commit_refresh(self, args: dict) -> object:
        return services.refresh_links(
            self._need_store(), str(args["kind"]), int(args["id"]), actor=self.actor
        )

    def _tool_plan_approve(self, args: dict) -> object:
        result = services.approve(
            self._need_store(),
            int(args["id"]),
            actor=self.actor,
            reason=str(args.get("reason") or ""),
            enforced=bool(args.get("enforce")),
        )
        return {
            "revision": asdict(result.revision),
            "created": result.created,
            "acknowledged": result.acknowledged,
        }

    def _tool_pull_request_refresh(self, args: dict) -> object:
        return services.refresh_forge(
            self._need_store(), str(args["kind"]), int(args["id"]), actor=self.actor
        )

    def _tool_pull_request_link(self, args: dict) -> object:
        parsed = parse_pull_url(str(args["url"]))
        if parsed is None:
            raise ValueError(f"not a GitHub pull request URL: {args['url']!r}")
        _ref, number = parsed
        title = str(args.get("title") or "") or f"PR #{number}"
        link = self._need_store().link_forge(
            str(args["kind"]),
            int(args["id"]),
            number,
            provider="github",
            kind="pull",
            url=str(args["url"]),
            title=title,
            state=str(args.get("state") or ""),
            actor=self.actor,
        )
        return vars(link)

    def _tool_pull_request_unlink(self, args: dict) -> object:
        ok = self._need_store().unlink_forge(
            str(args["kind"]), int(args["id"]), int(args["number"]), actor=self.actor
        )
        if not ok:
            raise KeyError(f"pull request {args['number']} not linked")
        return {"ok": True, "unlinked": args["number"]}

    def _tool_git_status(self, args: dict) -> object:
        return services.repo_statuses(self._need_store(), str(args["kind"]), int(args["id"]))

    def _tool_source_trail(self, args: dict) -> object:
        return asdict(build_source_trail(self._need_store(), str(args["kind"]), int(args["id"])))

    def _tool_commit_list(self, args: dict) -> object:
        return [
            vars(link)
            for link in self._need_store().effective_links(str(args["kind"]), int(args["id"]))
        ]

    def _tool_repo_list(self, args: dict) -> object:
        store = self._need_store()
        if bool(args.get("effective")):
            return store.effective_repos(str(args["kind"]), int(args["id"]))
        return store.list_repos(str(args["kind"]), int(args["id"]))

    def _tool_pull_request_list(self, args: dict) -> object:
        return [
            vars(link)
            for link in self._need_store().effective_forge_links(str(args["kind"]), int(args["id"]))
        ]

    def _tool_plan_diff(self, args: dict) -> object:
        result = services.diff(
            self._need_store(),
            int(args["id"]),
            from_revision=int(args["from_revision"]) if args.get("from_revision") else None,
            to_revision=int(args["to_revision"]) if args.get("to_revision") else None,
        )
        return {
            "plan": result.plan_id,
            "from_revision": result.from_revision.revision,
            "to_revision": result.to_revision.revision if result.to_revision else None,
            "entries": [asdict(entry) for entry in result.entries],
            "summary": result.summary,
        }

    def _tool_export_plan(self, args: dict) -> object:
        from lazyplan.presentation.shared.render import render_plan_markdown
        from lazyplan.services.transfer import export_plan

        entry = export_plan(self._need_store(), int(args["id"]))
        if entry is None:
            raise KeyError(f"plan {args['id']} not found")
        return {"plan": int(args["id"]), "markdown": render_plan_markdown(entry)}


__all__ = ["ProvenanceToolsMixin"]
