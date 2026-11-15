"""Bottom taskbar: key hints on the left, health and version on the right.

The badge reflects the running version and, when the update cache knows a
newer release, adds an arrow to it. Clicking the badge runs the app's update
action; it never checks the network itself.
"""

from __future__ import annotations

from typing import Any

from textual.content import Content
from textual.widgets import Static

from ....infrastructure.environment import UpgradeError, parse_version
from ...shared.design import escape_markup

VERSION_GAP = "  "


def version_text(running: str, latest: str = "") -> str:
    """Format the running version, adding a newer cached release when known."""
    current = running.strip().lstrip("vV")
    if not current:
        return ""
    label = f"v{current}"
    candidate = latest.strip().lstrip("vV")
    if not candidate:
        return label
    try:
        if parse_version(candidate) <= parse_version(current):
            return label
    except UpgradeError:
        return label
    return f"{label} → v{candidate}"


def badge_markup(text: str) -> str:
    """The clickable badge; an empty version renders nothing."""
    if not text:
        return ""
    return f"[@click=app.action_update_prompt]{escape_markup(text)}[/]"


def taskbar_markup(
    hints: str,
    *,
    health: str = "",
    running: str = "",
    latest: str = "",
    width: int = 80,
) -> str:
    """Compose one right-aligned taskbar line within *width* columns."""
    right = VERSION_GAP.join(
        part for part in (health, badge_markup(version_text(running, latest))) if part
    )
    if not right:
        return hints
    right_len = Content.from_markup(right).cell_length
    left = hints
    if Content.from_markup(left).cell_length + right_len + 1 > width:
        left = _truncate_hints(left, max(8, width - right_len - 2))
    gap = max(1, width - Content.from_markup(left).cell_length - right_len)
    return left + (" " * gap) + right


def _truncate_hints(hints: str, width: int) -> str:
    """Drop trailing hint items until the markup fits *width* columns."""
    parts = hints.split(" · ")
    while len(parts) > 1 and Content.from_markup(" · ".join(parts)).cell_length > width:
        parts.pop()
    return " · ".join(parts)


class Taskbar(Static):
    """One-line bar that keeps its badge pinned to the right edge."""

    def __init__(self, content: str = "", **kwargs: Any) -> None:
        super().__init__(content, markup=True, **kwargs)

    def set_line(
        self,
        hints: str,
        *,
        health: str = "",
        running: str = "",
        latest: str = "",
    ) -> None:
        """Repaint the line at the current widget width."""
        width = max(10, self.size.width or 80)
        self.update(
            taskbar_markup(
                hints,
                health=health,
                running=running,
                latest=latest,
                width=width,
            )
        )
