"""Row renderables shared by the tree and the spinner."""

from __future__ import annotations

from rich.text import Text


def row_text(markup: str) -> Text:
    """Parse one row's canonical markup once into a Rich Text renderable."""
    return Text.from_markup(markup)
