"""Model map transforms shared by the setup wizard and apply."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import replace
from pathlib import Path

from lazyplan.infrastructure import host_models, profiles
from lazyplan.infrastructure.host_models import HostCatalog

Discover = Callable[[Iterable[str], Path, Path | None], dict[str, HostCatalog]]


def initial_maps(
    db_path: str | Path,
    home: Path,
    root: Path | None,
    agents: list[str],
    discover: Discover | None = None,
) -> tuple[dict[str, profiles.Profile], dict[str, dict[str, str]]]:
    """The saved map plus discovered defaults for the selected hosts."""
    loaded, tiers = profiles.load_all(db_path)
    finder = discover or host_models.discover_all
    for host, catalog in finder(agents, home, root).items():
        for tier, model in catalog.tier_defaults.items():
            if model and not tiers.get(tier, {}).get(host):
                tiers.setdefault(tier, {})[host] = model
    return loaded, tiers


def apply_overrides(
    profiles_map: Mapping[str, profiles.Profile],
    tiers: Mapping[str, Mapping[str, str]],
    role_tiers: Mapping[str, str] | None = None,
    tier_models: Mapping[str, Mapping[str, str]] | None = None,
    role_models: Mapping[str, Mapping[str, str]] | None = None,
) -> tuple[dict[str, profiles.Profile], dict[str, dict[str, str]]]:
    """Apply host-first flag overrides to a map."""
    by_role: dict[str, dict[str, str]] = {}
    for host, roles in (role_models or {}).items():
        for role, model in roles.items():
            by_role.setdefault(role, {})[host] = model
    updated: dict[str, profiles.Profile] = {}
    for role, profile in profiles_map.items():
        tier = str((role_tiers or {}).get(role, profile.tier))
        models = dict(profile.models)
        models.update(by_role.get(role, {}))
        updated[role] = replace(profile, tier=tier, models=models)
    effective = {tier: dict(values) for tier, values in tiers.items()}
    for host, host_tiers in (tier_models or {}).items():
        for tier, model in host_tiers.items():
            effective.setdefault(tier, {})[host] = model
    return updated, effective
