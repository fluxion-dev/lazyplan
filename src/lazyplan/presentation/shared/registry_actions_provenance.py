"""Provenance and activity actions (stdlib only).

Split from ``registry_actions`` so every hand-written module stays under the
repository budget.
"""

from __future__ import annotations

from .registry_model import Action, action

PROVENANCE_ACTIONS: tuple[Action, ...] = (
    action(
        "criterion.edit",
        "Edit criterion",
        surfaces=("tui", "cli", "mcp"),
        route=("tree", "trust"),
        cli_paths=("criterion edit",),
        mcp_tool="criterion_edit",
    ),
    action(
        "evidence.list",
        "List criterion evidence",
        surfaces=("cli", "mcp"),
        route=("tree", "evidence"),
        cli_paths=("criterion evidence",),
        mcp_tool="criterion_evidence",
    ),
    action(
        "criterion.delete",
        "Delete criterion",
        surfaces=("tui", "cli", "mcp"),
        route=("tree", "trust"),
        cli_paths=("criterion delete",),
        mcp_tool="criterion_delete",
    ),
    action(
        "comment.edit",
        "Edit comment",
        surfaces=("tui", "cli", "mcp"),
        route=("tree", "coordination"),
        cli_paths=("comment edit",),
        mcp_tool="comment_edit",
    ),
    action(
        "view.pull_requests_hub",
        "Open pull request hub",
        "P",
        "selection",
        ("tui",),
        ("tree", "provenance"),
        ("pull-requests-hub",),
    ),
    action(
        "pull_request.list",
        "List pull requests",
        surfaces=("tui", "cli", "mcp"),
        route=("tree", "provenance"),
        cli_paths=("pr list",),
        mcp_tool="pull_request_list",
    ),
    action(
        "pull_request.refresh",
        "Refresh pull requests",
        surfaces=("tui", "cli", "mcp"),
        route=("tree", "provenance"),
        palette_ids=("refresh-prs",),
        cli_paths=("pr refresh",),
        mcp_tool="pull_request_refresh",
    ),
    action(
        "pull_request.link",
        "Link pull request",
        surfaces=("tui", "cli", "mcp"),
        route=("tree", "provenance"),
        palette_ids=("link-pr",),
        cli_paths=("pr link",),
        mcp_tool="pull_request_link",
    ),
    action(
        "pull_request.unlink",
        "Unlink pull request",
        surfaces=("tui", "cli", "mcp"),
        route=("tree", "provenance"),
        palette_ids=("unlink-pr",),
        cli_paths=("pr unlink",),
        mcp_tool="pull_request_unlink",
    ),
    action(
        "commit.open",
        "Open commit",
        surfaces=("tui",),
        route=("tree", "provenance"),
    ),
    action(
        "file.open",
        "Open changed file",
        surfaces=("tui",),
        route=("tree", "provenance"),
    ),
    action(
        "repo.open",
        "Open checkout",
        surfaces=("tui",),
        route=("tree", "source"),
    ),
    action(
        "event.list",
        "Open activity hub",
        "A",
        "global",
        ("tui", "cli", "mcp"),
        ("tree", "activity"),
        ("activity-hub",),
        cli_paths=("feed",),
        mcp_tool="activity_list",
    ),
    action(
        "event.open",
        "Open event target",
        surfaces=("tui",),
        route=("tree", "activity"),
    ),
)


__all__ = ["PROVENANCE_ACTIONS"]
