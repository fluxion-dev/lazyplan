"""Palette facade over the canonical information-architecture registry.

Every command, section, key, context, glossary word, and surface mapping lives
in ``registry.py``. This module keeps the historical palette import path stable
while the surfaces migrate, so existing code and tests need no changes.
"""

from __future__ import annotations

from .registry import (
    APP,
    COMMANDS,
    CREATE,
    EDIT,
    LEGACY_COMMANDS,
    NOUNS,
    PALETTE_COMMANDS,
    PALETTE_SECTIONS,
    SECTIONS,
    VERBS,
    VIEW,
    Command,
    matching,
    palette_commands,
    palette_sections,
)
from .registry import (
    by_command_id as by_id,
)

__all__ = [
    "APP",
    "COMMANDS",
    "CREATE",
    "Command",
    "EDIT",
    "LEGACY_COMMANDS",
    "NOUNS",
    "PALETTE_COMMANDS",
    "PALETTE_SECTIONS",
    "SECTIONS",
    "VERBS",
    "VIEW",
    "by_id",
    "matching",
    "palette_commands",
    "palette_sections",
]
