"""Canonical entities, namespaces, and the action row shape (stdlib only).

Split from ``registry_actions`` so every hand-written module stays under the
repository budget. The registry re-exports these names.
"""

from __future__ import annotations

from dataclasses import dataclass

ENTITIES: tuple[str, ...] = (
    "plan",
    "milestone",
    "task",
    "criterion",
    "evidence",
    "question",
    "reference",
    "claim",
    "agent",
    "note",
    "comment",
    "commit",
    "file",
    "pull_request",
    "repo",
    "event",
    "maintenance",
)

SURFACES: tuple[str, ...] = ("tui", "cli", "mcp", "docs")
NAMESPACES: tuple[str, ...] = (
    "app",
    "view",
    "row",
    "git",
    "source",
    "theme",
    "palette",
)
TAXONOMY: tuple[str, ...] = ENTITIES + NAMESPACES

#: Setup wizard steps, named by their question function.
SETUP_STEPS: tuple[str, ...] = (
    "ask_placement",
    "ask_agents",
    "ask_integrations",
    "ask_migration",
)

#: Host lifecycle events a hook can answer.
HOOK_EVENTS: tuple[str, ...] = (
    "session-start",
    "prompt-submit",
    "pre-tool",
    "post-tool",
    "stop",
    "session-end",
    "pre-compact",
)


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


def action(
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


__all__ = [
    "Action",
    "ENTITIES",
    "HOOK_EVENTS",
    "NAMESPACES",
    "SETUP_STEPS",
    "SURFACES",
    "TAXONOMY",
    "action",
]
