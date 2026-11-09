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
    ),
    action(
        "evidence.list",
        "List criterion evidence",
        surfaces=("cli", "mcp"),
        route=("tree", "evidence"),
    ),
    action(
        "criterion.delete",
        "Delete criterion",
        surfaces=("tui", "cli", "mcp"),
        route=("tree", "trust"),
    ),
    action(
        "comment.edit",
        "Edit comment",
        surfaces=("tui", "cli", "mcp"),
        route=("tree", "coordination"),
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
    ),
    action(
        "pull_request.refresh",
        "Refresh pull requests",
        surfaces=("tui", "cli", "mcp"),
        route=("tree", "provenance"),
        palette_ids=("refresh-prs",),
    ),
    action(
        "pull_request.link",
        "Link pull request",
        surfaces=("tui", "cli", "mcp"),
        route=("tree", "provenance"),
        palette_ids=("link-pr",),
    ),
    action(
        "pull_request.unlink",
        "Unlink pull request",
        surfaces=("tui", "cli", "mcp"),
        route=("tree", "provenance"),
        palette_ids=("unlink-pr",),
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
    ),
    action(
        "event.open",
        "Open event target",
        surfaces=("tui",),
        route=("tree", "activity"),
    ),
)


__all__ = ["PROVENANCE_ACTIONS"]
