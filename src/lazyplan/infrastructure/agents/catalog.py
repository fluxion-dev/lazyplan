"""Command-based agent catalog stored beside the shared lazyplan home."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .. import textfile
from ..repo import shared_home

CATALOG_NAME = "agents.json"
DEFAULT_KEY = "opencode"


@dataclass(frozen=True)
class AgentProfile:
    """One ACP agent command the workbench can launch."""

    key: str
    title: str
    command: tuple[str, ...]
    env: dict[str, str] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "title": self.title,
            "command": list(self.command),
            "env": dict(self.env),
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> AgentProfile:
        key = str(payload.get("key") or "").strip()
        command = payload.get("command")
        if not key:
            raise ValueError("agent key must not be empty")
        if not isinstance(command, list) or not command:
            raise ValueError(f"agent {key!r} needs a non-empty command list")
        env = payload.get("env")
        if env is not None and not isinstance(env, dict):
            raise ValueError(f"agent {key!r} env must be an object")
        return cls(
            key=key,
            title=str(payload.get("title") or key),
            command=tuple(str(part) for part in command),
            env={str(name): str(value) for name, value in (env or {}).items()},
        )


def default_profile() -> AgentProfile:
    """The built-in OpenCode entry."""
    return AgentProfile(DEFAULT_KEY, "OpenCode", ("opencode", "acp"))


def catalog_path(home: str | Path | None = None) -> Path:
    """Shared-home path for the agent catalog."""
    return shared_home(home) / CATALOG_NAME


def load_catalog(home: str | Path | None = None) -> tuple[list[AgentProfile], str]:
    """Load profiles and the default key; a missing file yields OpenCode."""
    path = catalog_path(home)
    if not path.is_file():
        return [default_profile()], DEFAULT_KEY
    try:
        payload = json.loads(textfile.read(path))
    except (OSError, ValueError) as exc:
        raise ValueError(f"cannot read agent catalog {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"agent catalog {path} must be an object")
    rows = payload.get("agents")
    if not isinstance(rows, list):
        raise ValueError(f"agent catalog {path} needs an agents list")
    profiles = [AgentProfile.from_payload(row) for row in rows if isinstance(row, dict)]
    if not profiles:
        profiles = [default_profile()]
    default = str(payload.get("default") or profiles[0].key)
    if default not in {profile.key for profile in profiles}:
        default = profiles[0].key
    return profiles, default


def save_catalog(
    profiles: list[AgentProfile],
    default: str,
    home: str | Path | None = None,
) -> Path:
    """Write the catalog atomically and return its path."""
    if not profiles:
        raise ValueError("agent catalog must keep at least one profile")
    keys = {profile.key for profile in profiles}
    if default not in keys:
        raise ValueError(f"default agent {default!r} is not in the catalog")
    path = catalog_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "default": default,
        "agents": [profile.to_payload() for profile in profiles],
    }
    textfile.write_atomic(path, json.dumps(payload, indent=2) + "\n")
    return path


def find_profile(
    key: str,
    home: str | Path | None = None,
) -> AgentProfile:
    """Resolve one profile by key, raising a readable error when absent."""
    profiles, _default = load_catalog(home)
    for profile in profiles:
        if profile.key == key:
            return profile
    known = ", ".join(profile.key for profile in profiles)
    raise KeyError(f"unknown agent {key!r}; choose one of: {known}")
