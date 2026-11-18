"""Fixed-width slots for tree rows.

The row renderer keeps the title flexible and reserves fixed right-aligned
slots for progress and the status rail. The status mark owns the last two
cells of the row, so the ID and title lead and the state stays in one column.
``stats_layout`` chooses the visible slots from the row width and kind; it
never depends on the mark or the emoji mode.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from .status import cell_width
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
    # The right rail holds one mark: two cells for emoji, one for the fallback.
    "state": StatSlot("state", 2, 1, "right"),
}

#: Slot priority per kind: the first slot that fits survives the narrowest row.
KIND_SLOTS: dict[str, tuple[str, ...]] = {
    "plan": ("state", "progress"),
    "milestone": ("state", "progress"),
    "task": ("state",),
}


@dataclass(frozen=True)
class RowStats:
    """One row's fixed slots: progress count and the right-rail mark."""

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
    if key == "state":
        return stats.state
    return ""


def _aligned(text: str, slot: StatSlot) -> str:
    """Pad to the slot in display cells, so an emoji keeps a two-cell rail."""
    gap = " " * max(0, slot.width - cell_width(text))
    return gap + text if slot.align == "right" else text + gap


def _slot_markup(key: str, aligned: str) -> str:
    return f"[dim]{aligned}[/]" if key == "progress" and aligned.strip() else aligned


def render_stats(stats: RowStats, layout: tuple[str, ...]) -> tuple[str, str]:
    """Render one fixed-width stats block as rich markup and plain text."""
    rich_parts: list[str] = []
    plain_parts: list[str] = []
    for key in layout:
        aligned = _aligned(_slot_text(stats, key), SLOTS[key])
        rich_parts.append(_slot_markup(key, aligned))
        plain_parts.append(aligned)
    return " ".join(rich_parts), " ".join(plain_parts)
