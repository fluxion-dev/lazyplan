"""Runtime settings read from flags and environment."""

from __future__ import annotations

import os

HEAL_OFF = "off"
HEAL_SAFE = "safe"
HEAL_STRICT = "strict"
_MODES = frozenset({HEAL_OFF, HEAL_SAFE, HEAL_STRICT})


def heal_mode(flag: bool | None = None) -> str:
    """Resolve --heal/--no-heal, then LAZYPLAN_HEAL, then safe."""
    if flag is not None:
        return HEAL_SAFE if flag else HEAL_OFF
    value = os.environ.get("LAZYPLAN_HEAL", "").strip().lower()
    return value if value in _MODES else HEAL_SAFE


def heal_enabled(mode: str) -> bool:
    """True when a mode performs automatic repair."""
    return mode != HEAL_OFF
