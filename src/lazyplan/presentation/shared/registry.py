"""Canonical information-architecture registry (stdlib only).

The registry is the single source for action IDs, labels, keys, contexts,
surfaces, routes, and palette aliases. Palette and help remain facades while
the surfaces migrate; tests reject duplicate IDs, key conflicts, orphans, and
routes deeper than three screens.
"""

from __future__ import annotations

from dataclasses import dataclass

from .legacy_commands import LEGACY_COMMANDS as LEGACY_COMMANDS
from .registry_commands import (
    APP,
    COMMANDS,
    CREATE,
    DISABLED_FOR,
    EDIT,
    NOUNS,
    PALETTE_COMMANDS,
    PALETTE_SECTIONS,
    SECTIONS,
    VERBS,
    VIEW,
    Command,
    Context,
    matching,
    palette_commands,
    palette_context,
    palette_sections,
)
from .registry_commands import (
    by_id as by_command_id,
)

ENTITIES: tuple[str, ...] = (
    "plan",
    "milestone",
    "task",
    "criterion",
    "evidence",
    "question",
    "reference",
    "claim",
    "session",
    "note",
    "comment",
    "commit",
    "file",
    "pull_request",
    "repo",
    "event",
    "override",
)

SURFACES: tuple[str, ...] = ("tui", "cli", "mcp", "docs")
NAMESPACES: tuple[str, ...] = (
    "app",
    "view",
    "row",
    "bulk",
    "git",
    "source",
    "theme",
    "palette",
)
TAXONOMY: tuple[str, ...] = ENTITIES + NAMESPACES


@dataclass(frozen=True)
class Action:
    """One canonical action and where it is reachable."""

    id: str
    label: str
    key: str = ""
    context: str = "global"
    surfaces: tuple[str, ...] = ("tui",)
    route: tuple[str, ...] = ("tree",)
    palette_ids: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    deprecated_in: str = ""
    removal: str = ""

    @property
    def taxonomy(self) -> str:
        """Taxonomy prefix: an entity or a UI namespace."""
        return self.id.split(".", 1)[0]


def _action(
    id: str,
    label: str,
    key: str = "",
    context: str = "global",
    surfaces: tuple[str, ...] = ("tui",),
    route: tuple[str, ...] = ("tree",),
    palette_ids: tuple[str, ...] = (),
) -> Action:
    """Build one registry row with stable defaults."""
    return Action(
        id=id,
        label=label,
        key=key,
        context=context,
        surfaces=surfaces,
        route=route,
        palette_ids=palette_ids,
    )


ACTIONS: tuple[Action, ...] = (
    _action(
        "plan.create",
        "Create plan",
        surfaces=("tui", "cli", "mcp"),
        route=("tree", "create"),
        palette_ids=("create-plan",),
    ),
    _action(
        "milestone.create",
        "Create milestone",
        surfaces=("tui", "cli", "mcp"),
        route=("tree", "create"),
        palette_ids=("create-milestone",),
    ),
    _action(
        "task.create",
        "Create task",
        surfaces=("tui", "cli", "mcp"),
        route=("tree", "create"),
        palette_ids=("create-task",),
    ),
    _action(
        "criterion.add",
        "Add criterion",
        "a",
        "tree",
        ("tui", "cli", "mcp"),
        ("tree", "detail"),
        ("add-criterion",),
    ),
    _action(
        "plan.approve",
        "Approve plan scope",
        surfaces=("tui", "cli"),
        route=("tree", "detail", "trust"),
        palette_ids=("approve-plan",),
    ),
    _action(
        "plan.diff",
        "Show plan diff",
        surfaces=("tui", "cli"),
        route=("tree", "detail", "trust"),
        palette_ids=("plan-diff",),
    ),
    _action(
        "criterion.prove",
        "Prove criterion",
        surfaces=("tui", "cli", "mcp"),
        route=("tree", "detail", "evidence"),
        palette_ids=("prove-criterion",),
    ),
    _action(
        "question.add",
        "Add plan question",
        surfaces=("tui", "cli", "mcp"),
        route=("tree", "detail", "questions"),
        palette_ids=("add-question",),
    ),
    _action(
        "question.resolve",
        "Resolve plan question",
        surfaces=("tui", "cli", "mcp"),
        route=("tree", "detail", "questions"),
        palette_ids=("resolve-question",),
    ),
    _action(
        "question.reopen",
        "Reopen plan question",
        surfaces=("tui", "cli", "mcp"),
        route=("tree", "detail", "questions"),
        palette_ids=("reopen-question",),
    ),
    _action(
        "reference.link",
        "Link external reference",
        surfaces=("tui", "cli", "mcp"),
        route=("tree", "detail", "references"),
        palette_ids=("link-ref",),
    ),
    _action(
        "reference.unlink",
        "Unlink external reference",
        surfaces=("tui", "cli", "mcp"),
        route=("tree", "detail", "references"),
        palette_ids=("unlink-ref",),
    ),
    _action(
        "task.claim",
        "Claim task",
        surfaces=("tui", "cli", "mcp"),
        route=("tree", "detail", "coordination"),
        palette_ids=("claim-task",),
    ),
    _action(
        "task.block",
        "Block task",
        surfaces=("tui", "cli", "mcp"),
        route=("tree", "detail", "coordination"),
        palette_ids=("block-task",),
    ),
    _action(
        "task.unblock",
        "Unblock task",
        surfaces=("tui", "cli", "mcp"),
        route=("tree", "detail", "coordination"),
        palette_ids=("unblock-task",),
    ),
    _action(
        "task.finish",
        "Finish task",
        surfaces=("tui", "cli", "mcp"),
        route=("tree", "detail", "finish"),
        palette_ids=("finish-task",),
    ),
    _action(
        "row.edit",
        "Edit selection",
        "e",
        "tree",
        ("tui", "cli"),
        ("tree", "detail"),
        ("edit-selection",),
    ),
    _action(
        "task.move",
        "Move task",
        "s",
        "tree",
        ("tui", "cli", "mcp"),
        ("tree", "detail"),
        ("move-todo", "move-doing", "move-done"),
    ),
    _action(
        "row.mark",
        "Mark/unmark row",
        "space",
        "tree",
        ("tui",),
        ("tree",),
        ("toggle-mark",),
    ),
    _action("row.clear_marks", "Clear marks", surfaces=("tui",), palette_ids=("clear-marks",)),
    _action(
        "claim.release",
        "Release claim",
        surfaces=("tui", "cli", "mcp"),
        route=("tree", "detail", "coordination"),
        palette_ids=("release-claim",),
    ),
    _action(
        "claim.force_release",
        "Force release claim",
        surfaces=("tui", "cli"),
        route=("tree", "detail", "coordination"),
        palette_ids=("force-release-claim",),
    ),
    _action(
        "criterion.tick",
        "Tick next criterion",
        "x",
        "tree",
        ("tui", "cli", "mcp"),
        ("tree", "detail"),
        ("tick-criterion",),
    ),
    _action(
        "criterion.untick",
        "Reopen last criterion",
        surfaces=("tui", "cli", "mcp"),
        route=("tree", "detail"),
        palette_ids=("untick-criterion",),
    ),
    _action(
        "row.delete",
        "Delete selection",
        "d",
        "tree",
        ("tui", "cli"),
        ("tree", "detail"),
        ("delete-selection",),
    ),
    _action(
        "commit.link",
        "Link current commit",
        surfaces=("tui", "cli"),
        route=("tree", "detail", "provenance"),
        palette_ids=("git-capture",),
    ),
    _action(
        "commit.refresh",
        "Refresh commit links",
        surfaces=("tui", "cli"),
        route=("tree", "detail", "provenance"),
        palette_ids=("git-refresh",),
    ),
    _action(
        "bulk.move",
        "Bulk move",
        surfaces=("tui",),
        palette_ids=("bulk-doing", "bulk-done"),
    ),
    _action("bulk.block", "Bulk block tasks", surfaces=("tui",), palette_ids=("bulk-block",)),
    _action(
        "bulk.release",
        "Bulk release claims",
        surfaces=("tui",),
        palette_ids=("bulk-release",),
    ),
    _action("bulk.undo", "Undo bulk change", surfaces=("tui",), palette_ids=("undo-bulk",)),
    _action(
        "view.detail",
        "Open detail",
        "enter",
        "tree",
        ("tui",),
        ("tree", "detail"),
        ("open-detail",),
    ),
    _action(
        "view.fold",
        "Fold/unfold row",
        "z",
        "tree",
        ("tui",),
        ("tree",),
        ("fold-one", "fold-all"),
    ),
    _action(
        "view.filter",
        "Filter by text",
        "/",
        "tree",
        ("tui",),
        ("tree",),
        ("filter-text",),
    ),
    _action(
        "view.plan_mode",
        "Change plan mode",
        "f",
        "tree",
        ("tui", "docs"),
        ("tree",),
        ("plan-mode",),
    ),
    _action(
        "view.refresh",
        "Refresh",
        "r",
        "tree",
        ("tui",),
        ("tree",),
        ("refresh",),
    ),
    _action(
        "git.status",
        "Show git status",
        surfaces=("tui", "cli"),
        route=("tree", "detail", "provenance"),
        palette_ids=("git-status",),
    ),
    _action(
        "pull_request.open",
        "Open pull request",
        surfaces=("tui",),
        route=("tree", "detail", "provenance"),
        palette_ids=("open-pr",),
    ),
    _action(
        "source.trail",
        "Open source trail",
        "g",
        "tree",
        ("tui",),
        ("tree", "source"),
        ("source-trail",),
    ),
    _action(
        "override.toggle",
        "Toggle manual override",
        "O",
        "global",
        ("tui",),
        ("tree",),
        ("toggle-override",),
    ),
    _action(
        "theme.cycle",
        "Cycle theme",
        "t",
        "global",
        ("tui",),
        ("tree",),
        ("cycle-theme",),
    ),
    _action(
        "palette.open",
        "Command palette",
        "c",
        "global",
        ("tui",),
        ("any",),
        ("command-palette",),
    ),
    _action(
        "plan.export",
        "Export plan as Markdown",
        surfaces=("tui", "cli"),
        route=("tree", "export"),
        palette_ids=("export-plan",),
    ),
    _action(
        "app.update",
        "Update lpui",
        "U",
        "global",
        ("tui", "cli"),
        ("tree", "update"),
        ("update-lpui",),
    ),
    _action(
        "app.help",
        "Help",
        "?",
        "global",
        ("tui", "cli", "docs"),
        ("any",),
        ("help",),
    ),
    _action("app.quit", "Quit", "q", "global", ("tui",), ("any",), ("quit",)),
)


PALETTE_TO_ACTION: dict[str, str] = {
    palette_id: action.id for action in ACTIONS for palette_id in action.palette_ids
}


def by_id(action_id: str) -> Action | None:
    """Look up one canonical action."""
    return next((action for action in ACTIONS if action.id == action_id), None)


__all__ = [
    "ACTIONS",
    "APP",
    "Action",
    "COMMANDS",
    "CREATE",
    "Command",
    "Context",
    "DISABLED_FOR",
    "EDIT",
    "ENTITIES",
    "LEGACY_COMMANDS",
    "NAMESPACES",
    "NOUNS",
    "PALETTE_COMMANDS",
    "PALETTE_SECTIONS",
    "PALETTE_TO_ACTION",
    "SECTIONS",
    "SURFACES",
    "TAXONOMY",
    "VERBS",
    "VIEW",
    "by_command_id",
    "by_id",
    "matching",
    "palette_commands",
    "palette_context",
    "palette_sections",
]
