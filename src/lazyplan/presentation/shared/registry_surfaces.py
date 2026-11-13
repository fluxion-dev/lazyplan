"""Canonical action adapters for the CLI and MCP surfaces (stdlib only).

The registry declares which surfaces should expose an action. This module is
the one mapping per surface: canonical action id to CLI command path or MCP
tool name. Actions that intentionally stay on one surface carry an explicit
exception with a reason, so the parity gate fails on an undocumented gap.
"""

from __future__ import annotations

from dataclasses import dataclass

CLI_ACTIONS: dict[str, tuple[str, ...]] = {
    "plan.create": ("plan add",),
    "milestone.create": ("milestone add",),
    "task.create": ("task add",),
    "criterion.add": ("criterion add",),
    "criterion.edit": ("criterion edit",),
    "criterion.delete": ("criterion delete",),
    "evidence.list": ("criterion evidence",),
    "plan.approve": ("plan approve",),
    "plan.diff": ("plan diff",),
    "criterion.prove": ("criterion prove",),
    "question.add": ("question add",),
    "question.resolve": ("question resolve",),
    "question.reopen": ("question reopen",),
    "reference.link": ("ref link",),
    "reference.unlink": ("ref unlink",),
    "task.claim": ("claim take",),
    "task.block": ("task block",),
    "task.unblock": ("task unblock",),
    "task.finish": ("task finish",),
    "task.renew": ("claim renew",),
    "row.edit": ("plan edit", "milestone edit", "task edit"),
    "task.move": ("plan move", "milestone move", "task move"),
    "claim.release": ("claim release",),
    "claim.force_release": ("claim release",),
    "criterion.relate": ("criterion relate",),
    "criterion.unrelate": ("criterion unrelate",),
    "row.delete": ("plan delete", "milestone delete", "task delete"),
    "commit.link": ("link",),
    "commit.refresh": ("commits",),
    "git.status": ("git status",),
    "source.trail": ("commits",),
    "plan.export": ("export",),
    "app.update": ("upgrade",),
    "app.notes": ("notes",),
    "app.health": ("doctor",),
    "app.help": ("help",),
    "task.touch_add": ("touch add",),
    "task.touch_remove": ("touch remove",),
    "note.add": ("note add",),
    "comment.add": ("comment add",),
    "comment.edit": ("comment edit",),
    "comment.resolve": ("comment resolve",),
    "pull_request.list": ("pr list",),
    "pull_request.refresh": ("pr refresh",),
    "pull_request.link": ("pr link",),
    "pull_request.unlink": ("pr unlink",),
    "event.list": ("feed",),
    "maintenance.report": ("maint report",),
    "maintenance.archive": ("maint archive",),
    "maintenance.trim": ("maint trim",),
    "maintenance.vacuum": ("maint vacuum",),
    "maintenance.restore": ("maint restore",),
}

MCP_ACTIONS: dict[str, str] = {
    "plan.create": "create_plan",
    "milestone.create": "create_milestone",
    "task.create": "create_task",
    "criterion.add": "criterion_add",
    "criterion.edit": "criterion_edit",
    "criterion.delete": "criterion_delete",
    "evidence.list": "criterion_evidence",
    "plan.approve": "plan_approve",
    "plan.diff": "plan_diff",
    "criterion.prove": "criterion_prove",
    "question.add": "question_add",
    "question.resolve": "question_resolve",
    "question.reopen": "question_reopen",
    "reference.link": "reference_link",
    "reference.unlink": "reference_unlink",
    "task.claim": "claim_task",
    "task.block": "block_task",
    "task.unblock": "unblock_task",
    "task.finish": "finish_task",
    "task.renew": "claim_renew",
    "row.edit": "edit_row",
    "task.move": "move_row",
    "claim.release": "claim_release",
    "claim.force_release": "claim_release",
    "criterion.relate": "criterion_relate",
    "criterion.unrelate": "criterion_unrelate",
    "row.delete": "delete_row",
    "commit.link": "link_commit",
    "commit.refresh": "commit_refresh",
    "git.status": "git_status",
    "source.trail": "source_trail",
    "plan.export": "export_plan",
    "task.touch_add": "touch_add",
    "task.touch_remove": "touch_remove",
    "note.add": "note_add",
    "comment.add": "comment_add",
    "comment.edit": "comment_edit",
    "comment.resolve": "comment_resolve",
    "pull_request.list": "pull_request_list",
    "pull_request.refresh": "pull_request_refresh",
    "pull_request.link": "pull_request_link",
    "pull_request.unlink": "pull_request_unlink",
    "event.list": "activity_list",
    "maintenance.report": "maintenance_report",
    "maintenance.archive": "maintenance_archive",
    "maintenance.trim": "maintenance_trim",
    "maintenance.vacuum": "maintenance_vacuum",
    "maintenance.restore": "maintenance_restore",
}


@dataclass(frozen=True)
class SurfaceException:
    """One approved missing path for an action on one surface."""

    action: str
    surface: str
    reason: str


#: Approved exceptions recorded in the IA spec's parity matrix.
SURFACE_EXCEPTIONS: tuple[SurfaceException, ...] = (
    SurfaceException("reference.open", "cli", "TUI opens the URL in a browser"),
    SurfaceException("reference.open", "mcp", "MCP never launches a browser"),
    SurfaceException("view.fold", "cli", "TUI-only tree gesture"),
    SurfaceException("view.fold", "mcp", "TUI-only tree gesture"),
    SurfaceException("view.filter", "cli", "CLI filters with `list --status`/`--repo`"),
    SurfaceException("view.filter", "mcp", "MCP reads a whole plan with `show_row`"),
    SurfaceException("view.criteria_hub", "cli", "CLI reads criteria with `criterion list`"),
    SurfaceException("view.criteria_hub", "mcp", "MCP reads criteria with `criterion list`"),
    SurfaceException("view.evidence_hub", "cli", "CLI reads evidence with `criterion evidence`"),
    SurfaceException("view.evidence_hub", "mcp", "MCP reads evidence with `criterion_evidence`"),
    SurfaceException("view.questions_hub", "cli", "CLI reads questions with `question list`"),
    SurfaceException("view.questions_hub", "mcp", "MCP reads questions with `question_list`"),
    SurfaceException("view.references_hub", "cli", "CLI reads refs with `ref list`"),
    SurfaceException("view.references_hub", "mcp", "MCP reads refs with `reference_list`"),
    SurfaceException("view.claims_hub", "cli", "CLI reads claims with `claims`"),
    SurfaceException("view.claims_hub", "mcp", "MCP reads claims with `claims`"),
    SurfaceException("view.agents_hub", "cli", "CLI lists claim holders with `claims`"),
    SurfaceException("view.agents_hub", "mcp", "MCP lists claim holders with `claims`"),
    SurfaceException("view.comments_hub", "cli", "CLI reads comments with `comment list`"),
    SurfaceException("view.comments_hub", "mcp", "MCP reads comments with `comment_list`"),
    SurfaceException("view.refresh", "cli", "CLI reads fresh data on every call"),
    SurfaceException("view.refresh", "mcp", "MCP reads fresh data on every call"),
    SurfaceException("pull_request.open", "cli", "CLI keeps URLs in `pr show`"),
    SurfaceException("pull_request.open", "mcp", "MCP never launches a browser"),
    SurfaceException("theme.cycle", "cli", "TUI-only appearance choice"),
    SurfaceException("theme.cycle", "mcp", "TUI-only appearance choice"),
    SurfaceException("palette.open", "cli", "TUI overlay; CLI has named commands"),
    SurfaceException("palette.open", "mcp", "TUI overlay; MCP has typed tools"),
    SurfaceException("app.help", "mcp", "MCP has no overlay; tool schemas carry help"),
    SurfaceException("app.quit", "cli", "CLI exits when the command finishes"),
    SurfaceException("app.quit", "mcp", "MCP sessions close by closing the transport"),
    SurfaceException("commit.open", "cli", "CLI lists commits with `commits`"),
    SurfaceException("commit.open", "mcp", "MCP lists commits with `commit_list`"),
    SurfaceException("file.open", "cli", "CLI lists files with `commits --files`"),
    SurfaceException("file.open", "mcp", "MCP lists files with `commit_list`"),
    SurfaceException("repo.open", "cli", "CLI lists repos with `repos`"),
    SurfaceException("repo.open", "mcp", "MCP lists repos with `repo_list`"),
    SurfaceException("event.open", "cli", "CLI output carries the target ids"),
    SurfaceException("event.open", "mcp", "MCP output carries the target ids"),
)


def cli_paths(action_id: str) -> tuple[str, ...]:
    """CLI command paths for one action."""
    return CLI_ACTIONS.get(action_id, ())


def mcp_tool(action_id: str) -> str:
    """MCP tool name for one action, or an empty string."""
    return MCP_ACTIONS.get(action_id, "")


def exception_for(action_id: str, surface: str) -> SurfaceException | None:
    """The approved exception for one action/surface pair, if any."""
    return next(
        (row for row in SURFACE_EXCEPTIONS if row.action == action_id and row.surface == surface),
        None,
    )


def uncovered(actions: tuple, surfaces: tuple[str, ...] = ("cli", "mcp")) -> list[str]:
    """Action/surface pairs with neither a mapping nor a recorded exception."""
    found: list[str] = []
    for action in actions:
        for surface in surfaces:
            if surface not in action.surfaces:
                continue
            mapped = bool(cli_paths(action.id)) if surface == "cli" else bool(mcp_tool(action.id))
            if mapped or exception_for(action.id, surface) is not None:
                continue
            found.append(f"{action.id}: {surface}")
    return found


__all__ = [
    "CLI_ACTIONS",
    "MCP_ACTIONS",
    "SURFACE_EXCEPTIONS",
    "SurfaceException",
    "cli_paths",
    "exception_for",
    "mcp_tool",
    "uncovered",
]
