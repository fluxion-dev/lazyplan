"""Registry-derived CLI group inventory.

The parser keeps hand-written option definitions, but the noun groups and the
verbs they must expose come from the surface registry. Tests compare the built
parser against this inventory, so a new registry path cannot silently drift.
"""

from __future__ import annotations

from ...shared.registry_surfaces import CLI_ACTIONS

#: Top-level groups whose actions are one noun plus one verb.
CORE_GROUPS = (
    "plan",
    "milestone",
    "task",
    "criterion",
    "question",
    "session",
    "touch",
    "ref",
    "claim",
    "issue",
    "git",
    "pr",
)


def cli_group_actions() -> dict[str, tuple[str, ...]]:
    """Return every noun group and its verbs, derived from CLI action paths."""
    found: dict[str, set[str]] = {noun: set() for noun in CORE_GROUPS}
    for paths in CLI_ACTIONS.values():
        for path in paths:
            parts = path.split()
            if len(parts) != 2:
                continue
            noun, verb = parts
            if noun in found:
                found[noun].add(verb)
    return {noun: tuple(sorted(verbs)) for noun, verbs in found.items()}


def group_blurb(noun: str) -> str:
    """One help line for a noun group, generated from its registry verbs."""
    verbs = cli_group_actions().get(noun, ())
    return f"{', '.join(verbs)} a {noun}" if verbs else f"actions on a {noun}"
