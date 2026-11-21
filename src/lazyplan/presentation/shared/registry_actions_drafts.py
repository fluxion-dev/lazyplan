"""Draft review actions (stdlib only).

Split from ``registry_actions`` so every hand-written module stays under the
repository budget.
"""

from __future__ import annotations

from .registry_model import Action, action

DRAFT_ACTIONS: tuple[Action, ...] = (
    action(
        "draft.open",
        "Open plan draft",
        context="selection",
        surfaces=("tui", "cli", "mcp"),
        route=("tree", "draft"),
        palette_ids=("open-draft",),
        cli_paths=("draft show",),
        mcp_tool="draft_show",
    ),
    action(
        "draft.promote",
        "Promote plan draft",
        surfaces=("tui", "cli", "mcp"),
        route=("draft", "promote"),
        palette_ids=("promote-draft",),
        cli_paths=("draft promote",),
        mcp_tool="draft_promote",
    ),
)


__all__ = ["DRAFT_ACTIONS"]
