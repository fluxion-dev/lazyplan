"""Read-only inspection of installed and pending integrations.

Setup resolves the remembered layout, then compares the shipped catalog
with the files on disk and the choices remembered in ``setup.json``. This
module never writes: review and apply live in the setup flow.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from lazyplan.infrastructure import hook_install, skills
from lazyplan.infrastructure.integrations import (
    SKILL,
    IntegrationItem,
    catalog,
    hook_id,
    skill_paths,
)

from .layout import SetupChoice
from .state import SetupState

__all__ = [
    "Inspection",
    "inspect",
]


@dataclass(frozen=True)
class Inspection:
    """Installed and pending catalog items for one setup context."""

    installed: tuple[IntegrationItem, ...]
    pending: tuple[IntegrationItem, ...]


def _installed_ids(
    choice: SetupChoice,
    root: Path | None,
    home: Path,
    items: tuple[IntegrationItem, ...],
) -> set[str]:
    """Return catalog ids whose files are present, without writing."""
    installed: set[str] = set()
    plan = skills.plan_choice(choice, root, home)
    if plan.scope != "none":
        for item in items:
            if item.kind != SKILL:
                continue
            paths = skill_paths(
                item,
                plan.scope,
                root,
                home,
                plan.tools,
                plan.skills_dir,
            )
            if any(path.is_file() for path in paths):
                installed.add(item.id)
    for host in hook_install.HOSTS:
        for event in hook_install.installed_events(home, host):
            installed.add(hook_id(host, event))
    return installed


def _enabled(item: IntegrationItem, state: SetupState, choice: SetupChoice) -> bool:
    if item.kind == SKILL:
        return state.skills_enabled and not choice.no_skills
    return state.hooks_enabled


def _pending(
    item: IntegrationItem,
    state: SetupState,
    installed: set[str],
    version: str,
) -> bool:
    if item.id in installed:
        return False
    remembered = state.integration_choices.get(item.id)
    if remembered is None:
        return True
    changed = bool(remembered.get("fingerprint")) and (
        remembered.get("fingerprint") != item.fingerprint
    )
    decision = remembered.get("decision")
    if decision == "installed":
        return False
    if decision == "never":
        return changed
    if decision == "deferred":
        return changed or remembered.get("version", "") != version
    return True


def inspect(
    choice: SetupChoice,
    state: SetupState,
    root: Path | None,
    home: Path | None = None,
    version: str = "",
) -> Inspection:
    """Return installed and pending catalog items for the remembered setup."""
    home = home or Path.home()
    items = catalog(home)
    installed_ids = _installed_ids(choice, root, home, items)
    installed = tuple(item for item in items if item.id in installed_ids)
    pending = tuple(
        item
        for item in items
        if _enabled(item, state, choice) and _pending(item, state, installed_ids, version)
    )
    return Inspection(installed=installed, pending=pending)
