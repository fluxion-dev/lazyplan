"""Canonical information-architecture registry (stdlib only).

The registry is the single source for action IDs, labels, keys, contexts,
surfaces, routes, and palette aliases. Palette and help remain facades while
the surfaces migrate; tests reject duplicate IDs, key conflicts, orphans, and
routes deeper than three screens.
"""

from __future__ import annotations

from dataclasses import dataclass

from .legacy_commands import LEGACY_COMMANDS as LEGACY_COMMANDS
from .registry_actions import (
    ACTIONS,
    ENTITIES,
    HOOK_EVENTS,
    NAMESPACES,
    PALETTE_TO_ACTION,
    SETUP_STEPS,
    SURFACES,
    TAXONOMY,
    Action,
    by_id,
)
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
from .registry_surfaces import (
    CLI_ACTIONS,
    MCP_ACTIONS,
    SURFACE_EXCEPTIONS,
    SurfaceException,
    cli_paths,
    exception_for,
    mcp_tool,
    uncovered,
)

#: Hub actions, in reading order; labels come from ACTIONS.
HUB_ACTIONS: dict[str, tuple[str, ...]] = {
    "criteria": (
        "criterion.add",
        "criterion.edit",
        "criterion.prove",
        "criterion.relate",
        "criterion.unrelate",
        "criterion.delete",
        "row.delete",
    ),
    "evidence": ("criterion.prove", "source.trail"),
    "questions": ("question.add", "question.resolve", "question.reopen"),
    "references": ("reference.link", "reference.unlink", "reference.open"),
    "claims": (
        "task.claim",
        "task.renew",
        "claim.release",
        "claim.force_release",
        "task.touch_add",
        "task.touch_remove",
    ),
    "sessions": ("session.start", "session.end"),
    "comments": ("comment.add", "comment.edit", "note.add", "comment.resolve"),
    "pull_requests": (
        "pull_request.list",
        "pull_request.refresh",
        "pull_request.link",
        "pull_request.unlink",
        "pull_request.open",
    ),
    "activity": ("event.open",),
}


def hub_actions(kind: str) -> tuple[tuple[str, str], ...]:
    """(action id, label) pairs for one hub, in registry order."""
    pairs: list[tuple[str, str]] = []
    for action_id in HUB_ACTIONS.get(kind, ()):
        action = by_id(action_id)
        if action is not None:
            pairs.append((action.id, action.label))
    return tuple(pairs)


def route_depth(action: Action) -> int:
    """Interactions from the main tree to this action's destination."""
    if action.route and action.route[0] in ("tree", "any"):
        return len(action.route) - 1
    return len(action.route)


def check_reachability(actions: tuple[Action, ...] = ACTIONS, max_depth: int = 3) -> list[str]:
    """Return one error per route that breaks the depth budget."""
    errors: list[str] = []
    for action in actions:
        depth = route_depth(action)
        if depth > max_depth:
            path = " › ".join(action.route)
            errors.append(f"{action.id}: {' › '.join(action.route)} is {depth} steps ({path})")
    return errors


def reachability_report(max_depth: int = 3) -> dict[str, object]:
    """Machine-readable depth per action and entity for the validation gate."""
    rows = [
        {"id": action.id, "route": list(action.route), "depth": route_depth(action)}
        for action in ACTIONS
    ]
    entities = {
        entity: min(
            (route_depth(action) for action in ACTIONS if action.taxonomy == entity),
            default=None,
        )
        for entity in ENTITIES
    }
    return {
        "max_depth": max_depth,
        "actions": rows,
        "entities": entities,
        "over_budget": check_reachability(ACTIONS, max_depth),
    }


DEPRECATION_RELEASE = "0.37.0"


@dataclass(frozen=True)
class Deprecation:
    """One legacy path, its replacement, and the release that removes it."""

    name: str
    replacement: str
    removal: str = DEPRECATION_RELEASE
    kind: str = "command"


#: Keys that moved during the navigation migration.
DEPRECATED_KEYS: tuple[Deprecation, ...] = (
    Deprecation("q (detail)", "Q adds a question; q quits", kind="key"),
    Deprecation("Q (detail)", "ctrl+r resolves a question", kind="key"),
)


def deprecations() -> tuple[Deprecation, ...]:
    """Every legacy command alias plus the moved keys."""
    commands = tuple(
        Deprecation(f"lpui {alias}", f"lpui {noun} {verb}".strip())
        for (noun, verb), aliases in LEGACY_COMMANDS.items()
        for alias in aliases
        if noun or alias != verb
    )
    return commands + DEPRECATED_KEYS


def key_deprecations() -> tuple[Deprecation, ...]:
    """The moved-key rows shown in help."""
    return DEPRECATED_KEYS


def legacy_notice(command: str) -> str | None:
    """A human stderr notice for a deprecated CLI verb, or None."""
    for dep in deprecations():
        if dep.kind == "command" and dep.name == f"lpui {command}":
            return (
                f"deprecated: {dep.name} is deprecated; use `{dep.replacement}` "
                f"(removed in {dep.removal})"
            )
    return None


__all__ = [
    "ACTIONS",
    "APP",
    "Action",
    "CLI_ACTIONS",
    "COMMANDS",
    "CREATE",
    "Command",
    "Context",
    "DEPRECATED_KEYS",
    "DEPRECATION_RELEASE",
    "DISABLED_FOR",
    "EDIT",
    "ENTITIES",
    "HOOK_EVENTS",
    "HUB_ACTIONS",
    "Deprecation",
    "LEGACY_COMMANDS",
    "MCP_ACTIONS",
    "NAMESPACES",
    "NOUNS",
    "PALETTE_COMMANDS",
    "PALETTE_SECTIONS",
    "PALETTE_TO_ACTION",
    "SECTIONS",
    "SETUP_STEPS",
    "SURFACES",
    "SURFACE_EXCEPTIONS",
    "SurfaceException",
    "TAXONOMY",
    "VERBS",
    "VIEW",
    "by_command_id",
    "by_id",
    "check_reachability",
    "cli_paths",
    "deprecations",
    "exception_for",
    "hub_actions",
    "key_deprecations",
    "legacy_notice",
    "matching",
    "mcp_tool",
    "palette_commands",
    "palette_context",
    "palette_sections",
    "reachability_report",
    "route_depth",
    "uncovered",
]
