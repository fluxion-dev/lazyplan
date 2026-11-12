"""Typed mutable state owned by the TUI app.

The app shell, mixins, and future controllers read and write this object.
Keeping the state in one place makes refreshes and tests independent of the
widget tree.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .navigation import NavigationHistory


@dataclass
class AppState:
    """Selection, mode, marks, folds, and transient shell flags."""

    selected: tuple[str, int] | None = None
    filter_text: str = ""
    collapsed: set[tuple[str, int]] = field(default_factory=set)
    expanded: set[tuple[str, int]] = field(default_factory=set)
    filter_snapshot: tuple[set[tuple[str, int]], set[tuple[str, int]]] | None = None
    preview_key: tuple[str, int] | None = None
    dirty_external: bool = False
    pending_note: str = ""
    mounted: bool = False
    refreshing: bool = False
    narrow: bool | None = None
    compact: bool = False
    wide: bool = False
    timeline_visible: bool = False

    def timeline_shown(self, narrow: bool) -> bool:
        """True when the timeline should be visible at this width."""
        return self.timeline_visible and not narrow

    history: NavigationHistory = field(default_factory=NavigationHistory)
