"""Typed mutable state owned by the TUI app.

The app shell, mixins, and future controllers read and write this object.
Keeping the state in one place makes refreshes and tests independent of the
widget tree.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class PlanMode(StrEnum):
    """Which plans the tree shows."""

    ACTIVE = "active"
    FINISHED = "finished"
    BOTH = "both"


_MODE_ORDER = (PlanMode.ACTIVE, PlanMode.FINISHED, PlanMode.BOTH)


def next_mode(mode: PlanMode) -> PlanMode:
    """Cycle Active -> Finished -> Both -> Active."""
    return _MODE_ORDER[(_MODE_ORDER.index(mode) + 1) % len(_MODE_ORDER)]


@dataclass
class AppState:
    """Selection, mode, marks, folds, and transient shell flags."""

    selected: tuple[str, int] | None = None
    plan_mode: PlanMode = PlanMode.ACTIVE
    filter_text: str = ""
    override_mode: bool = False
    override_warned: bool = False
    marked: set[tuple[str, int]] = field(default_factory=set)
    collapsed: set[tuple[str, int]] = field(default_factory=set)
    expanded: set[tuple[str, int]] = field(default_factory=set)
    preview_key: tuple[str, int] | None = None
    dirty_external: bool = False
    pending_note: str = ""
    mounted: bool = False
    refreshing: bool = False
    narrow: bool | None = None
    compact: bool = False
    wide: bool = False
