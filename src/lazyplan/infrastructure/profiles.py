"""Agent profile map: role tiers and per-host model targets.

``agents.json`` lives beside the database. Missing entries fall back to the
packaged defaults, so a partial file never erases the rest of the map. The
role definition stays host-agnostic: a role names a capability tier, and the
``tiers`` table maps that tier to each host's concrete model.

Stdlib only.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from ..core.policies.agents import (
    CLAUDE_MODELS,
    DEFAULT_MODELS,
    DEFAULT_ROLE_TIERS,
    HOSTS,
    TIERS,
)
from ..core.policies.lanes import AGENT_ROLES
from . import textfile
from .data_text import data_text

DEFAULT_TIERS = DEFAULT_ROLE_TIERS

FILE_NAME = "agents.json"
SCHEMA = 2
_PROFILE_FIELDS = {"tier", "model", "effort", "models"}
_TOP_FIELDS = {"schema", "tiers", "profiles"}


class ProfileError(ValueError):
    """The profile map is missing, malformed, or names an unknown key."""


@dataclass(frozen=True)
class Profile:
    """One role's model tier and optional host overrides."""

    role: str
    tier: str = "standard"
    model: str = ""
    effort: str = ""
    models: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        """JSON-safe payload."""
        return {
            "role": self.role,
            "tier": self.tier,
            "model": self.model,
            "effort": self.effort,
            "models": dict(self.models),
        }


def path_for(db_path: str | Path) -> Path:
    """The profile map beside a database."""
    return Path(db_path).expanduser().parent / FILE_NAME


def defaults() -> dict[str, Profile]:
    """The packaged profile map."""
    profiles, _tiers = _parse(data_text(FILE_NAME), "packaged agents.json")
    return profiles


def default_tiers() -> dict[str, dict[str, str]]:
    """The packaged tier-to-host model table."""
    _profiles, tiers = _parse(data_text(FILE_NAME), "packaged agents.json")
    return tiers


def load(db_path: str | Path) -> dict[str, Profile]:
    """The effective role map: packaged defaults plus the beside-DB file."""
    profiles, _tiers = load_all(db_path)
    return profiles


def load_all(
    db_path: str | Path,
) -> tuple[dict[str, Profile], dict[str, dict[str, str]]]:
    """The effective role map and tier table for one database."""
    profiles = defaults()
    tiers = default_tiers()
    path = path_for(db_path)
    if not path.is_file():
        return profiles, tiers
    try:
        text = textfile.read(path)
    except OSError as exc:
        raise ProfileError(f"cannot read {path}: {exc}") from exc
    override_profiles, override_tiers = _parse(text, str(path))
    profiles.update(override_profiles)
    for tier, targets in override_tiers.items():
        tiers.setdefault(tier, {}).update(targets)
    return profiles, tiers


def resolve(
    profile: Profile,
    host: str,
    models: Mapping[str, str] | None = None,
    tiers: Mapping[str, Mapping[str, str]] | None = None,
) -> dict[str, str]:
    """Resolve one profile to a host's model and effort hints.

    Precedence: per-role per-host override, per-role all-host override, the
    tier's host target, then a host default supplied by the caller. OpenCode's
    legacy ``main`` and ``small`` defaults still work when no tier target is
    present.
    """
    if host not in HOSTS:
        raise ProfileError(f"unknown host {host!r}; expected {'|'.join(HOSTS)}")
    chosen = models or {}
    tier_map = (tiers or {}).get(profile.tier, {})
    model = profile.models.get(host, "").strip()
    if not model:
        model = profile.model.strip()
    if not model:
        model = str(tier_map.get(host, "") or "").strip()
    if not model and host == "claude":
        model = CLAUDE_MODELS.get(profile.tier, "")
    if not model and host == "opencode" and ("main" in chosen or "small" in chosen):
        model = chosen.get("small" if profile.tier == "fast" else "main", "")
    if not model:
        model = str(chosen.get(host, "") or "").strip()
    return {
        "role": profile.role,
        "tier": profile.tier,
        "model": model,
        "effort": profile.effort,
    }


def resolve_all(
    profiles: Mapping[str, Profile],
    tiers: Mapping[str, Mapping[str, str]] | None = None,
    models: Mapping[str, str] | None = None,
) -> dict[str, dict[str, str]]:
    """Resolve every role for every host using one map."""
    out: dict[str, dict[str, str]] = {}
    for role, profile in profiles.items():
        resolved = {host: resolve(profile, host, models, tiers)["model"] for host in HOSTS}
        out[role] = {
            "tier": profile.tier,
            "effort": profile.effort,
            "models": resolved,
        }
        out[role].update(resolved)
    return out


def dispatch_profiles(db_path: str | Path, home: Path | None = None) -> dict[str, dict[str, str]]:
    """Resolved role profiles for the dispatch manifest."""
    profiles, tiers = load_all(db_path)
    return resolve_all(profiles, tiers, opencode_models(home or Path.home()))


def opencode_models(home: Path, repo_root: Path | None = None) -> dict[str, str]:
    """Read the configured main and small OpenCode models, when present."""
    candidates: list[Path] = []
    if repo_root is not None:
        candidates.extend([repo_root / "opencode.json", repo_root / "opencode.jsonc"])
    candidates.append(home / ".config" / "opencode" / "opencode.json")
    for path in candidates:
        if not path.is_file():
            continue
        try:
            text = textfile.read(path)
        except OSError:
            continue
        main = _json_field(text, "model")
        small = _json_field(text, "small_model")
        if main or small:
            return {"main": main, "small": small or main}
    return {}


def save(
    db_path: str | Path,
    profiles: Mapping[str, Profile],
    tiers: Mapping[str, Mapping[str, str]],
) -> Path:
    """Write one normalized schema 2 map atomically and return its path."""
    path = path_for(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    textfile.write(tmp, render(profiles, tiers))
    os.replace(tmp, path)
    return path


def render(
    profiles: Mapping[str, Profile],
    tiers: Mapping[str, Mapping[str, str]],
) -> str:
    """Render the normalized JSON text for a map."""
    payload = {
        "schema": SCHEMA,
        "tiers": {
            tier: {host: str((tiers.get(tier) or {}).get(host, "") or "") for host in HOSTS}
            for tier in TIERS
        },
        "profiles": {
            role: {
                "tier": profile.tier,
                "model": profile.model,
                "effort": profile.effort,
                "models": {host: profile.models[host] for host in HOSTS if host in profile.models},
            }
            for role, profile in profiles.items()
        },
    }
    return json.dumps(payload, indent=2) + "\n"


def _json_field(text: str, name: str) -> str:
    """One top-level string field from JSON or JSONC."""
    match = re.search(rf'"{re.escape(name)}"\s*:\s*"([^"]+)"', text)
    return match.group(1) if match is not None else ""


def _parse(
    text: str,
    source: str,
) -> tuple[dict[str, Profile], dict[str, dict[str, str]]]:
    """Parse one profile document, rejecting unknown roles, hosts, and tiers."""
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProfileError(f"{source}: invalid JSON: {exc.msg}") from exc
    if not isinstance(raw, dict):
        raise ProfileError(f"{source}: expected a JSON object")
    unknown_top = sorted(set(raw) - _TOP_FIELDS)
    if unknown_top:
        raise ProfileError(f"{source}: unknown top-level fields: {unknown_top}")
    profiles_raw = raw.get("profiles")
    if not isinstance(profiles_raw, dict):
        raise ProfileError(f"{source}: expected a 'profiles' object")
    tiers = _parse_tiers(raw.get("tiers"), source)
    out: dict[str, Profile] = {}
    for role, entry in profiles_raw.items():
        if role not in AGENT_ROLES:
            raise ProfileError(f"{source}: unknown role {role!r}")
        if not isinstance(entry, dict):
            raise ProfileError(f"{source}: profile {role!r} must be an object")
        unknown = sorted(set(entry) - _PROFILE_FIELDS)
        if unknown:
            raise ProfileError(f"{source}: profile {role!r} has unknown fields: {unknown}")
        tier = str(entry.get("tier") or DEFAULT_TIERS.get(role, "standard")).strip().lower()
        if tier not in TIERS:
            raise ProfileError(f"{source}: profile {role!r} tier must be {'|'.join(TIERS)}")
        models = _parse_models(entry.get("models"), f"{source}: profile {role!r}")
        out[role] = Profile(
            role=role,
            tier=tier,
            model=str(entry.get("model") or "").strip(),
            effort=str(entry.get("effort") or "").strip(),
            models=models,
        )
    return out, tiers


def _parse_tiers(raw: object, source: str) -> dict[str, dict[str, str]]:
    """Parse an optional tier table; absent tiers keep packaged defaults."""
    if raw is None:
        return {tier: dict(DEFAULT_MODELS[tier]) for tier in TIERS}
    if not isinstance(raw, dict):
        raise ProfileError(f"{source}: 'tiers' must be an object")
    unknown = sorted(set(raw) - set(TIERS))
    if unknown:
        raise ProfileError(f"{source}: unknown tiers: {unknown}")
    out: dict[str, dict[str, str]] = {tier: dict(DEFAULT_MODELS[tier]) for tier in TIERS}
    for tier, entry in raw.items():
        if not isinstance(entry, dict):
            raise ProfileError(f"{source}: tier {tier!r} must be an object")
        for host, value in entry.items():
            if host not in HOSTS:
                raise ProfileError(f"{source}: tier {tier!r} has unknown host {host!r}")
            if not isinstance(value, str):
                raise ProfileError(f"{source}: tier {tier!r} host {host!r} must be a string")
            out[tier][host] = value.strip()
    return out


def _parse_models(raw: object, source: str) -> dict[str, str]:
    """Parse one role's optional per-host overrides."""
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ProfileError(f"{source} models must be an object")
    out: dict[str, str] = {}
    for host, value in raw.items():
        if host not in HOSTS:
            raise ProfileError(f"{source} models has unknown host {host!r}")
        if not isinstance(value, str):
            raise ProfileError(f"{source} models host {host!r} must be a string")
        if value.strip():
            out[host] = value.strip()
    return out
