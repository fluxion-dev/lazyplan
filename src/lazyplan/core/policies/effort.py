"""Curated effort levels and the hosts that can render them.

Roles store one level; each host decides whether it has a field for it. An
empty level means inherit. Unknown strings stay readable so an older
``agents.json`` keeps working until the role is edited.
"""

from __future__ import annotations

INHERIT = ""
LOW = "low"
MEDIUM = "medium"
HIGH = "high"
LEVELS: tuple[str, ...] = (INHERIT, LOW, MEDIUM, HIGH)
LABELS: dict[str, str] = {
    INHERIT: "inherit",
    LOW: "low",
    MEDIUM: "medium",
    HIGH: "high",
}
HOST_FIELDS: dict[str, str] = {
    "claude": "effort",
    "codex": "model_reasoning_effort",
    "opencode": "variant",
}
LEVEL_ERROR = "effort must be inherit|low|medium|high"


def normalize(value: object) -> str:
    """Read a stored effort as a level; aliases for inherit become empty."""
    text = str(value or "").strip().lower()
    if text in ("inherit", "none", "default"):
        return INHERIT
    return text


def check(value: object) -> str:
    """Return a curated level or raise, for an edit made in the wizard."""
    level = normalize(value)
    if level not in LEVELS:
        raise ValueError(LEVEL_ERROR)
    return level


def supports(host: str) -> bool:
    """True when the host has a native field for the level."""
    return host in HOST_FIELDS


def field_for(host: str) -> str:
    """The host's field name, or an empty string when unsupported."""
    return HOST_FIELDS.get(host, "")


def label(value: object) -> str:
    """The display label for a stored value; unknown values show as-is."""
    level = str(value or "").strip()
    return LABELS.get(level, level or LABELS[INHERIT])
