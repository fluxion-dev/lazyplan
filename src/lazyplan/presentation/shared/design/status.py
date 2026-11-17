"""Status presentation: one emoji language with a single-cell fallback.

The TUI renders one status mark per row. A wide, UTF-8 terminal gets the
emoji; a terminal narrower than :data:`EMOJI_MIN_WIDTH` columns or one marked
ASCII-safe gets the single-cell glyph. The CLI never uses this module's emoji:
its labels stay on the plain fallback glyph.

Mapping:

    state         emoji  fallback  label
    todo          📝     ○         not-started
    doing         🔨     ◐         doing
    review        🔍     ?         review
    blocked       🚧     !         blocked
    done          ✅     ●         done

Review semantics: a completed plan shown in the plan review panel reads
``review``; a completed task reads ``done``. Blocking wins over every other
state, so a blocked row never claims to be doing or done.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

from ....core.entities import Status

#: Emoji are only safe when the terminal has room for a two-cell mark.
EMOJI_MIN_WIDTH = 80


@dataclass(frozen=True)
class StatusMark:
    """One state's full presentation: emoji, fallback glyph, and label."""

    emoji: str
    glyph: str
    label: str


STATUS_MARKS: dict[str, StatusMark] = {
    "todo": StatusMark("📝", "○", "not-started"),
    "doing": StatusMark("🔨", "◐", "doing"),
    "review": StatusMark("🔍", "?", "review"),
    "blocked": StatusMark("🚧", "!", "blocked"),
    "done": StatusMark("✅", "●", "done"),
}

STATUS_EMOJI = {state: mark.emoji for state, mark in STATUS_MARKS.items()}
STATUS_FALLBACK = {state: mark.glyph for state, mark in STATUS_MARKS.items()}
STATUS_LABEL = {state: mark.label for state, mark in STATUS_MARKS.items()}

#: CLI labels keep the three lifecycle glyphs they have always used.
STATUS_GLYPH = {state: STATUS_FALLBACK[state] for state in ("todo", "doing", "done")}
STATUS_ANSI = {"todo": "90", "doing": "33", "done": "32"}
STATUS_RICH = {"todo": "dim", "doing": "yellow", "done": "green"}


def status_key(value: Status | str) -> str:
    """The plain status value for an enum or string."""
    return value.value if isinstance(value, Status) else str(value)


def status_state(
    status: Status | str,
    *,
    blocked: bool = False,
    review: bool = False,
    attention: bool = False,
) -> str:
    """Resolve one row to exactly one presentation state.

    Priority: blocked, explicit plan-review, done, attention (review), doing,
    todo. Done outranks attention so a completed task stays ``done``; the
    plan review panel passes ``review=True`` for completed plans instead.
    """
    name = status_key(status)
    if blocked or name == "blocked":
        return "blocked"
    if review:
        return "review"
    if name == "done":
        return "done"
    if attention or name == "review":
        return "review"
    if name == "doing":
        return "doing"
    return "todo"


def status_mark(state: Status | str, *, emoji: bool = True) -> str:
    """The emoji or single-cell fallback glyph for one presentation state."""
    mark = STATUS_MARKS.get(status_key(state), STATUS_MARKS["review"])
    return mark.emoji if emoji else mark.glyph


def status_label(state: Status | str) -> str:
    """Plain word for one presentation state, for docs and tests."""
    return STATUS_MARKS.get(status_key(state), STATUS_MARKS["review"]).label


def ascii_safe_environment() -> bool:
    """True when the current terminal is marked ASCII-only.

    ``TERM=dumb`` is the established shell marker. A non-UTF stream cannot
    encode emoji, so it falls back as well. Emoji support is otherwise
    assumed; there is no perfect terminal probe.
    """
    if os.environ.get("TERM", "").strip().lower() in ("dumb", "unknown"):
        return True
    for stream in (sys.stdout, sys.stderr):
        encoding = (getattr(stream, "encoding", "") or "").strip().lower()
        if encoding and not encoding.startswith("utf"):
            return True
    return False


def emoji_enabled(width: int | None, *, ascii_safe: bool | None = None) -> bool:
    """Choose emoji only for a wide terminal that can render them."""
    if ascii_safe is None:
        ascii_safe = ascii_safe_environment()
    if ascii_safe:
        return False
    return width is None or width >= EMOJI_MIN_WIDTH


def mark_width(emoji: bool) -> int:
    """Cells reserved by one status mark before the separating space."""
    return 2 if emoji else 1


def cell_width(text: str) -> int:
    """Display cells for status-aware row math.

    Rich owns the width table; the fallback keeps this module usable on a
    stdlib-only interpreter where only the CLI's plain labels render.
    """
    try:
        from rich.cells import cell_len
    except ImportError:  # pragma: no cover - stdlib-only interpreter
        return len(text)
    return cell_len(text)


__all__ = [
    "EMOJI_MIN_WIDTH",
    "STATUS_ANSI",
    "STATUS_EMOJI",
    "STATUS_FALLBACK",
    "STATUS_GLYPH",
    "STATUS_LABEL",
    "STATUS_MARKS",
    "STATUS_RICH",
    "StatusMark",
    "ascii_safe_environment",
    "cell_width",
    "emoji_enabled",
    "mark_width",
    "status_key",
    "status_label",
    "status_mark",
    "status_state",
]
