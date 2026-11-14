"""Agent profile map: one model tier and optional overrides per role.

``agents.json`` lives beside the database. Missing entries fall back to the
packaged defaults, so a partial file never erases the rest of the map.
Stdlib only.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from ..core.policies.lanes import AGENT_ROLES
from .data_text import data_text

FILE_NAME = "agents.json"
TIERS = ("fast", "standard", "deep")
DEFAULT_TIERS: dict[str, str] = {
    "scout": "fast",
    "implementer": "fast",
    "qa": "standard",
    "refactor": "standard",
    "docs": "fast",
    "reviewer": "deep",
    "integrator": "deep",
}
CLAUDE_MODELS: dict[str, str] = {
    "fast": "haiku",
    "standard": "sonnet",
    "deep": "opus",
}
_FIELDS = {"tier", "model", "effort"}


class ProfileError(ValueError):
    """The profile map is missing, malformed, or names an unknown role."""


@dataclass(frozen=True)
class Profile:
    """One role's model tier and optional host overrides."""

    role: str
    tier: str = "standard"
    model: str = ""
    effort: str = ""

    def to_dict(self) -> dict[str, str]:
        """JSON-safe payload."""
        return {
            "role": self.role,
            "tier": self.tier,
            "model": self.model,
            "effort": self.effort,
        }


def path_for(db_path: str | Path) -> Path:
    """The profile map beside a database."""
    return Path(db_path).expanduser().parent / FILE_NAME


def defaults() -> dict[str, Profile]:
    """The packaged profile map."""
    return _parse(data_text(FILE_NAME), "packaged agents.json")


def load(db_path: str | Path) -> dict[str, Profile]:
    """The effective map: packaged defaults with the beside-DB file applied."""
    profiles = defaults()
    path = path_for(db_path)
    if not path.is_file():
        return profiles
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ProfileError(f"cannot read {path}: {exc}") from exc
    override = _parse(text, str(path))
    profiles.update(override)
    return profiles


def resolve(
    profile: Profile,
    host: str,
    models: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Resolve one profile to a host's model and effort hints."""
    chosen = models or {}
    if profile.model:
        model = profile.model
    elif host == "claude":
        model = CLAUDE_MODELS.get(profile.tier, "")
    elif host == "opencode":
        model = chosen.get("small", "") if profile.tier == "fast" else chosen.get("main", "")
    else:
        model = ""
    return {
        "role": profile.role,
        "tier": profile.tier,
        "model": model,
        "effort": profile.effort,
    }


def dispatch_profiles(db_path: str | Path, home: Path | None = None) -> dict[str, dict[str, str]]:
    """Resolved role profiles for the dispatch manifest."""
    loaded = load(db_path)
    models = opencode_models(home or Path.home())
    out: dict[str, dict[str, str]] = {}
    for role, profile in loaded.items():
        out[role] = {
            "tier": profile.tier,
            "effort": profile.effort,
            "opencode": resolve(profile, "opencode", models)["model"],
            "claude": resolve(profile, "claude")["model"],
        }
    return out


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
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        main = _json_field(text, "model")
        small = _json_field(text, "small_model")
        if main or small:
            return {"main": main, "small": small or main}
    return {}


def _json_field(text: str, name: str) -> str:
    """One top-level string field from JSON or JSONC."""
    match = re.search(rf'"{re.escape(name)}"\s*:\s*"([^"]+)"', text)
    return match.group(1) if match is not None else ""


def _parse(text: str, source: str) -> dict[str, Profile]:
    """Parse one profile document, rejecting unknown roles and fields."""
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProfileError(f"{source}: invalid JSON: {exc.msg}") from exc
    if not isinstance(raw, dict) or not isinstance(raw.get("profiles"), dict):
        raise ProfileError(f"{source}: expected a 'profiles' object")
    out: dict[str, Profile] = {}
    for role, entry in raw["profiles"].items():
        if role not in AGENT_ROLES:
            raise ProfileError(f"{source}: unknown role {role!r}")
        if not isinstance(entry, dict):
            raise ProfileError(f"{source}: profile {role!r} must be an object")
        unknown = sorted(set(entry) - _FIELDS)
        if unknown:
            raise ProfileError(f"{source}: profile {role!r} has unknown fields: {unknown}")
        tier = str(entry.get("tier") or DEFAULT_TIERS.get(role, "standard")).strip().lower()
        if tier not in TIERS:
            raise ProfileError(f"{source}: profile {role!r} tier must be {'|'.join(TIERS)}")
        out[role] = Profile(
            role=role,
            tier=tier,
            model=str(entry.get("model") or "").strip(),
            effort=str(entry.get("effort") or "").strip(),
        )
    return out
