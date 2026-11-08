"""Catalog of installable agent integrations.

The catalog is a pure description of the skills and hook surfaces this
release can install. Setup compares it with installed files and remembered
choices so an upgrade can offer only the items a release added.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from . import hook_hosts, hook_install, skills

SKILL = "skill"
HOOK = "hook"
PLUGIN_EVENT = "plugin"

HOST_LABELS: dict[str, str] = {
    "opencode": "OpenCode",
    "claude": "Claude Code",
    "gemini": "Gemini CLI",
    "codex": "Codex",
    "cursor": "Cursor",
}

__all__ = [
    "HOOK",
    "HOST_LABELS",
    "IntegrationItem",
    "PLUGIN_EVENT",
    "SKILL",
    "catalog",
    "hook_id",
    "hook_paths",
    "skill_id",
    "skill_paths",
]


def skill_id(name: str) -> str:
    """Stable catalog id for one skill."""
    return f"{SKILL}:{name}"


def hook_id(host: str, event: str) -> str:
    """Stable catalog id for one hook event."""
    return f"{HOOK}:{host}:{event}"


@dataclass(frozen=True)
class IntegrationItem:
    """One shipped skill or hook event."""

    id: str
    kind: str
    label: str
    fingerprint: str
    host: str = ""
    event: str = ""
    skill: str = ""

    def to_dict(self) -> dict[str, str]:
        """Return a JSON-safe summary."""
        return {
            "id": self.id,
            "kind": self.kind,
            "label": self.label,
            "fingerprint": self.fingerprint,
            "host": self.host,
            "event": self.event,
            "skill": self.skill,
        }


def _fingerprint(payload: object) -> str:
    text = json.dumps(payload, ensure_ascii=True, sort_keys=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def _skill_item(spec: skills.SkillSpec) -> IntegrationItem:
    return IntegrationItem(
        id=skill_id(spec.name),
        kind=SKILL,
        label=f"{spec.name} skill",
        fingerprint=_fingerprint({"name": spec.name, "text": skills.render_skill(spec.name)}),
        skill=spec.name,
    )


def _plugin_item(host: str) -> IntegrationItem:
    return IntegrationItem(
        id=hook_id(host, PLUGIN_EVENT),
        kind=HOOK,
        label=f"{HOST_LABELS.get(host, host)} plugin",
        fingerprint=_fingerprint(
            {
                "plugin": hook_install.PLUGIN_NAME,
                "text": hook_install.plugin_text(),
            }
        ),
        host=host,
        event=PLUGIN_EVENT,
    )


def _event_item(host: str, event: str, native: str, surface: str) -> IntegrationItem:
    return IntegrationItem(
        id=hook_id(host, event),
        kind=HOOK,
        label=f"{HOST_LABELS.get(host, host)} {event}",
        fingerprint=_fingerprint(
            {
                "host": host,
                "event": event,
                "native": native,
                "matcher": hook_hosts.matcher(host, native),
                "command": hook_install.command(host, event),
                "surface": surface,
            }
        ),
        host=host,
        event=event,
    )


def catalog(home: Path | None = None) -> tuple[IntegrationItem, ...]:
    """Return every shipped integration in stable order."""
    home = home or Path.home()
    surfaces = {spec.host: spec.kind for spec in hook_install.specs(home)}
    items = [_skill_item(spec) for spec in skills.SKILLS]
    for host in hook_install.HOSTS:
        surface = surfaces.get(host, "")
        if surface == "plugin":
            items.append(_plugin_item(host))
            continue
        for event, native in hook_hosts.EVENTS.get(host, {}).items():
            items.append(_event_item(host, event, native, surface))
    return tuple(items)


def hook_paths(item: IntegrationItem, home: Path | None = None) -> list[Path]:
    """Return the host files one hook item writes, without touching them."""
    if item.kind != HOOK:
        return []
    home = home or Path.home()
    return [spec.path for spec in hook_install.specs(home) if spec.host == item.host]


def skill_paths(
    item: IntegrationItem,
    scope: str,
    repo_root: Path | None,
    home: Path | None = None,
    tools: list[str] | None = None,
    skills_dir: str | Path | None = None,
) -> list[Path]:
    """Return the SKILL.md files one skill item writes, without touching them."""
    if item.kind != SKILL:
        return []
    home = home or Path.home()
    return skills.skill_destinations(
        scope,
        repo_root,
        home,
        tools,
        skills_dir,
        name=item.skill,
    )
