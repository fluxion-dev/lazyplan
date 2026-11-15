"""Model map transforms shared by the setup wizard and apply."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path

from lazyplan.infrastructure import host_models, profiles


def initial_maps(
    db_path: str | Path,
    home: Path,
    root: Path | None,
    agents: list[str],
) -> tuple[dict[str, profiles.Profile], dict[str, dict[str, str]]]:
    """The saved map plus discovered defaults for the selected hosts."""
    loaded, _saved = profiles.load_all(db_path)
    tiers = host_models.effective_tiers(db_path, home, root, agents)
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
