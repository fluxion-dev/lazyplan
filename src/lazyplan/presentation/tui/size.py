"""One place that decides the shell's width and height tiers.

Screens must not re-derive 80/100/120/30. Every surface reads
:func:`classes_for` and applies the names it paints with, so the resize matrix
and the stylesheets agree on what ``compact``, ``wide``, ``short``, ``narrow``,
and ``stacked`` mean.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

NARROW_WIDTH = 100
COMPACT_WIDTH = 80
WIDE_WIDTH = 120
SHORT_HEIGHT = 30


@dataclass(frozen=True)
class SizeClasses:
    """The tiers for one terminal rectangle."""

    narrow: bool
    compact: bool
    wide: bool
    short: bool
    stacked: bool


def classes_for(width: int, height: int | None = None) -> SizeClasses:
    """Classify a terminal *width* and optional *height*.

    ``stacked`` is the point where a two-pane split gives up and stacks; it
    tracks ``narrow`` because both describe "too tight for two columns".
    """
    narrow = width < NARROW_WIDTH
    return SizeClasses(
        narrow=narrow,
        compact=width < COMPACT_WIDTH,
        wide=width >= WIDE_WIDTH,
        short=height is not None and height < SHORT_HEIGHT,
        stacked=narrow,
    )


def apply_classes(node: Any, classes: SizeClasses, names: Iterable[str]) -> None:
    """Set the named CSS classes on *node* from *classes*."""
    for name in names:
        node.set_class(getattr(classes, name), name)
