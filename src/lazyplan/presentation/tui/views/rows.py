"""Row renderables shared by the tree and the spinner."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from rich.text import Text

from ....core.entities import Status


@dataclass(frozen=True)
class RowSpec:
    """One tree row that can render at any width."""

    render: Callable[..., str]
    depth: int
    status: Status

    def markup(self, width: int) -> str:
        """Return this row's Rich markup at *width* cells."""
        return self.render(width=width)


def row_text(markup: str) -> Text:
    """Parse one row's canonical markup once into a Rich Text renderable."""
    return Text.from_markup(markup)
