"""Fixed-width stat slots for tree rows.

The row renderer keeps the title flexible and places every stat in a fixed
slot. Missing stats reserve blanks, so the stats block start and right edge do
not move when a row changes state. `stats_layout` chooses the visible slots
from the row width and kind; it never depends on state.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from itertools import product

from .text import progress_bar, progress_text, truncate

TITLE_MIN = 8
SLOT_GAP = 1
FULL_BONUS = 5
COMPACT_PENALTY = 10


@dataclass(frozen=True)
class StatSlot:
    """One fixed-width column in the row stats block."""

    key: str
    width: int
    compact_width: int
    weight: int
    order: int
    align: str


SLOTS: dict[str, StatSlot] = {
    "progress": StatSlot("progress", 11, 8, 1000, 0, "left"),
    "attention": StatSlot("attention", 1, 1, 900, 1, "right"),
}

KIND_SLOTS: dict[str, tuple[str, ...]] = {
    "plan": ("progress", "attention"),
    "milestone": ("progress", "attention"),
    "task": ("attention",),
}


@dataclass(frozen=True)
class RowStats:
    """State values rendered into the fixed tree row slots."""

    progress: tuple[int, int] | None = None
    attention: bool = False


def _slot_width(key: str, compact: bool) -> int:
    slot = SLOTS[key]
    return slot.compact_width if compact else slot.width


def _layout_width(layout: tuple[tuple[str, bool], ...]) -> int:
    if not layout:
        return 0
    return sum(_slot_width(key, compact) for key, compact in layout) + SLOT_GAP * (len(layout) - 1)


def _layout_score(layout: tuple[tuple[str, bool], ...]) -> tuple[int, int, int]:
    weight = sum(
        SLOTS[key].weight + (0 if compact else FULL_BONUS) - (COMPACT_PENALTY if compact else 0)
        for key, compact in layout
    )
    compact_count = sum(1 for _key, compact in layout if compact)
    return weight, -compact_count, len(layout)


@lru_cache(maxsize=1024)
def stats_layout(kind: str, width: int, prefix_width: int) -> tuple[tuple[str, bool], ...]:
    """Choose the visible slots for one row width; state never affects it."""
    budget = width - prefix_width - TITLE_MIN
    if budget <= 0:
        return ()
    keys = KIND_SLOTS[kind]
    best: tuple[tuple[str, bool], ...] = ()
    best_score: tuple[int, int, int] | None = None
    for choices in product((None, False, True), repeat=len(keys)):
        layout = tuple(
            (key, bool(compact))
            for key, compact in zip(keys, choices, strict=True)
            if compact is not None
        )
        if _layout_width(layout) > budget:
            continue
        score = _layout_score(layout)
        if best_score is None or score > best_score:
            best = layout
            best_score = score
    return tuple(sorted(best, key=lambda item: SLOTS[item[0]].order))


def _align(text: str, width: int, align: str) -> str:
    return text.rjust(width) if align == "right" else text.ljust(width)


def _progress_slot(stats: RowStats, compact: bool) -> tuple[str, str]:
    bar_width = 3 if compact else 5
    count_width = 4 if compact else 5
    done, total = stats.progress or (0, 0)
    bar = progress_bar(done, total, width=bar_width).ljust(bar_width)
    count = truncate(progress_text(done, total), count_width).rjust(count_width)
    text = f"{bar} {count}"
    return f"[dim]{text}[/]", text


def _attention_slot(stats: RowStats, compact: bool) -> tuple[str, str]:
    del compact
    return ("[yellow]![/]" if stats.attention else ""), ("!" if stats.attention else "")


_SLOT_RENDERERS: dict[str, Callable[[RowStats, bool], tuple[str, str]]] = {
    "progress": _progress_slot,
    "attention": _attention_slot,
}


def _slot_text(stats: RowStats, key: str, compact: bool) -> tuple[str, str]:
    renderer = _SLOT_RENDERERS.get(key)
    return renderer(stats, compact) if renderer is not None else ("", "")


def render_stats(stats: RowStats, layout: tuple[tuple[str, bool], ...]) -> tuple[str, str]:
    """Render one fixed-width stats block as rich markup and plain text."""
    rich_parts: list[str] = []
    plain_parts: list[str] = []
    for key, compact in layout:
        rich, plain = _slot_text(stats, key, compact)
        width = _slot_width(key, compact)
        aligned = _align(plain, width, SLOTS[key].align)
        padding = width - len(plain)
        if SLOTS[key].align == "right":
            rich = " " * padding + rich
        else:
            rich = rich + " " * padding
        rich_parts.append(rich)
        plain_parts.append(aligned)
    return " ".join(rich_parts), " ".join(plain_parts)
