"""Fixed-width word slots for tree rows.

The row renderer keeps the title flexible and places counts and state words in
fixed right-aligned slots. Missing values reserve blanks, so the stats block
start and right edge do not move when a row changes state. ``stats_layout``
chooses the visible slots from the row width and kind; it never depends on
state.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from .text import progress_text, truncate

TITLE_MIN = 8
SLOT_GAP = 1


@dataclass(frozen=True)
class StatSlot:
    """One fixed-width column in the row stats block."""

    key: str
    width: int
    order: int
    align: str


SLOTS: dict[str, StatSlot] = {
    "progress": StatSlot("progress", 5, 0, "right"),
    "state": StatSlot("state", 7, 1, "right"),
}

#: Slot priority per kind: the first slot that fits survives the narrowest row.
KIND_SLOTS: dict[str, tuple[str, ...]] = {
    "plan": ("state", "progress"),
    "milestone": ("state", "progress"),
    "task": ("state",),
}


@dataclass(frozen=True)
class RowStats:
    """Word values rendered into the fixed tree row slots."""

    progress: tuple[int, int] | None = None
    state: str = ""


def _layout_width(layout: tuple[str, ...]) -> int:
    if not layout:
        return 0
    return sum(SLOTS[key].width for key in layout) + SLOT_GAP * (len(layout) - 1)


@lru_cache(maxsize=1024)
def stats_layout(kind: str, width: int, prefix_width: int) -> tuple[str, ...]:
    """Choose the visible slots for one row width; state never affects it."""
    budget = width - prefix_width - TITLE_MIN
    chosen: list[str] = []
    for key in KIND_SLOTS[kind]:
        need = SLOTS[key].width + (SLOT_GAP if chosen else 0)
        if budget <= 0 or _layout_width(tuple(chosen)) + need > budget:
            continue
        chosen.append(key)
    return tuple(sorted(chosen, key=lambda key: SLOTS[key].order))


def _slot_text(stats: RowStats, key: str) -> str:
    if key == "progress":
        done, total = stats.progress or (0, 0)
        return truncate(progress_text(done, total), SLOTS[key].width)
    return truncate(stats.state, SLOTS[key].width)


def _aligned(text: str, slot: StatSlot) -> str:
    return text.rjust(slot.width) if slot.align == "right" else text.ljust(slot.width)


def _slot_markup(stats: RowStats, key: str) -> str:
    slot = SLOTS[key]
    text = _slot_text(stats, key)
    aligned = _aligned(text, slot)
    return f"[dim]{aligned}[/]" if key == "progress" and text else aligned


def render_stats(stats: RowStats, layout: tuple[str, ...]) -> tuple[str, str]:
    """Render one fixed-width stats block as rich markup and plain text."""
    rich_parts = [_slot_markup(stats, key) for key in layout]
    plain_parts = [_aligned(_slot_text(stats, key), SLOTS[key]) for key in layout]
    return " ".join(rich_parts), " ".join(plain_parts)
