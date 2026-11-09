"""CLI commands for the ACP agent catalog."""

from __future__ import annotations

import json
from argparse import Namespace

from ....infrastructure.agents import (
    AgentProfile,
    catalog_path,
    load_catalog,
    save_catalog,
)
from ....store import Store


def _print_error(message: str) -> int:
    print(f"error: {message}")
    return 2


def _cmd_agent_list(_store: Store | None, args: Namespace, _actor: str) -> int:
    """List configured agents and mark the default."""
    try:
        profiles, default = load_catalog()
    except ValueError as exc:
        return _print_error(str(exc))
    if getattr(args, "json", False):
        payload = {
            "path": str(catalog_path()),
            "default": default,
            "agents": [profile.to_payload() for profile in profiles],
        }
        print(json.dumps(payload, indent=2))
        return 0
    print(f"catalog: {catalog_path()}")
    for profile in profiles:
        marker = "*" if profile.key == default else " "
        command = " ".join(profile.command)
        print(f"{marker} {profile.key:<12} {profile.title:<20} {command}")
    return 0


def _cmd_agent_add(_store: Store | None, args: Namespace, _actor: str) -> int:
    """Add one agent profile without replacing an existing key."""
    key = str(args.key).strip()
    if not key:
        return _print_error("agent key must not be empty")
    try:
        profiles, default = load_catalog()
    except ValueError as exc:
        return _print_error(str(exc))
    if any(profile.key == key for profile in profiles):
        return _print_error(f"agent {key!r} already exists")
    env: dict[str, str] = {}
    for item in args.env:
        name, separator, value = str(item).partition("=")
        if not separator or not name.strip():
            return _print_error(f"bad --env {item!r}; use NAME=VALUE")
        env[name.strip()] = value
    command = [str(args.executable), *(str(part) for part in args.args)]
    profile = AgentProfile(
        key=key,
        title=str(args.title or key),
        command=tuple(command),
        env=env,
    )
    profiles.append(profile)
    if args.default:
        default = key
    path = save_catalog(profiles, default)
    print(f"added {key} to {path}")
    return 0


def _cmd_agent_remove(_store: Store | None, args: Namespace, _actor: str) -> int:
    """Remove one agent profile; keep at least one and a valid default."""
    key = str(args.key).strip()
    try:
        profiles, default = load_catalog()
    except ValueError as exc:
        return _print_error(str(exc))
    remaining = [profile for profile in profiles if profile.key != key]
    if len(remaining) == len(profiles):
        return _print_error(f"unknown agent {key!r}")
    if not remaining:
        return _print_error("cannot remove the last agent")
    if default == key:
        default = remaining[0].key
    path = save_catalog(remaining, default)
    print(f"removed {key} from {path}; default is {default}")
    return 0
