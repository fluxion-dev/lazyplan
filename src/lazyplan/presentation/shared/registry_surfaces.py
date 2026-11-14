"""Canonical action adapters for the CLI and MCP surfaces (stdlib only).

The registry declares which surfaces should expose an action, and each
``Action`` row carries its CLI command paths and MCP tool name, so the maps
below are derived once instead of maintained in parallel. Actions that
intentionally stay on one surface carry an explicit exception with a reason,
so the parity gate fails on an undocumented gap.
"""

from __future__ import annotations

from dataclasses import dataclass

from .registry_actions import ACTIONS

CLI_ACTIONS: dict[str, tuple[str, ...]] = {
    action.id: action.cli_paths for action in ACTIONS if action.cli_paths
}

MCP_ACTIONS: dict[str, str] = {action.id: action.mcp_tool for action in ACTIONS if action.mcp_tool}


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
    SurfaceException("view.agents_hub", "cli", "CLI reads agents with `agent list`"),
    SurfaceException("view.agents_hub", "mcp", "MCP reads agents with `agent_list`"),
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
    SurfaceException("agent.start", "mcp", "MCP stays read-only for agent lifecycle"),
    SurfaceException("agent.end", "mcp", "MCP stays read-only for agent lifecycle"),
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
