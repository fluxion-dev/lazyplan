"""Small building blocks shared by the setup wizard step panels.

Rows, labels, notes, and the focus search repeat across every step. They live
here so the screen classes stay thin; the copy and behaviour stay in the
screen. Textual is optional like every other screen module.
"""

from __future__ import annotations

import re
from typing import Any

try:
    from textual.containers import Horizontal
    from textual.widgets import Label, Static

    _TEXTUAL_OK = True
except ImportError:  # pragma: no cover - stdlib-only interpreter
    _TEXTUAL_OK = False


def widget_id(text: str) -> str:
    """Turn a catalog id into a Textual widget id."""
    return re.sub(r"[^A-Za-z0-9_-]+", "-", text).strip("-")


if _TEXTUAL_OK:

    def note(text: str, *, markup: bool = True) -> Static:
        """One muted explanation line."""
        return Static(text, classes="setup-note", markup=markup)

    def host_label(text: str) -> Static:
        """One bold section or host heading."""
        return Static(text, classes="setup-host")

    def row(label: str, *widgets: Any) -> Horizontal:
        """One labelled control row (stacked by the compact CSS)."""
        return Horizontal(
            Label(label, classes="setup-row-label"),
            *widgets,
            classes="setup-row",
        )

    def list_block(lines: list[str]) -> Static:
        """One indented block of review lines."""
        return Static("\n".join(f"  {line}" for line in lines), classes="setup-list")

    def first_focusable(node: Any) -> Any:
        """The first widget in *node* that can take focus, depth first."""
        for child in getattr(node, "children", ()):
            if getattr(child, "can_focus", False) and not getattr(child, "disabled", False):
                return child
            found = first_focusable(child)
            if found is not None:
                return found
        return None
