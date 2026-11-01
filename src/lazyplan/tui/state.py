"""Typed mutable state owned by the TUI app.

The app shell, mixins, and future controllers read and write this object.
Keeping the state in one place makes refreshes and tests independent of the
widget tree.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..models import Status


@dataclass
class AppState:
    """Selection, filters, marks, folds, and transient shell flags."""

    selected: tuple[str, int] | None = None
    status_filter: Status | None = None
    show_all: bool = False
    filter_text: str = ""
    source_filter: str = "all"
    marked: set[tuple[str, int]] = field(default_factory=set)
    collapsed: set[tuple[str, int]] = field(default_factory=set)
    expanded: set[tuple[str, int]] = field(default_factory=set)
    preview_key: tuple[str, int] | None = None
    dirty_external: bool = False
    pending_note: str = ""
    mounted: bool = False
    refreshing: bool = False
    narrow: bool | None = None
