"""Agent host and capability-tier vocabulary shared by profiles and setup.

Roles stay host-agnostic: a role names a tier, and the tier table maps that
tier to each host's concrete model. Stdlib only.
"""

from __future__ import annotations

HOSTS: tuple[str, ...] = ("opencode", "claude", "codex", "gemini", "cursor", "copilot")
TIERS: tuple[str, ...] = ("fast", "standard", "deep")

DEFAULT_ROLE_TIERS: dict[str, str] = {
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

#: Packaged tier targets: host-specific defaults that a user file can override.
DEFAULT_MODELS: dict[str, dict[str, str]] = {
    "fast": {
        "opencode": "",
        "claude": "haiku",
        "codex": "",
        "gemini": "",
        "cursor": "",
        "copilot": "",
    },
    "standard": {
        "opencode": "",
        "claude": "sonnet",
        "codex": "",
        "gemini": "",
        "cursor": "",
        "copilot": "",
    },
    "deep": {
        "opencode": "",
        "claude": "opus",
        "codex": "",
        "gemini": "",
        "cursor": "",
        "copilot": "",
    },
}
