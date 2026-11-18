"""Draft block selections: turn a Textual range into a stable anchor."""

from __future__ import annotations

from textual.geometry import Offset
from textual.selection import Selection

from ....services.draft_content import DraftAnchor, DraftBlock


def _line_start(text: str, line: int) -> int:
    """Absolute offset where one split-lines line begins."""
    return sum(len(row) for row in text.splitlines(keepends=True)[:line])


def selection_offsets(text: str, selection: Selection) -> tuple[int, int]:
    """Absolute start/end offsets for one text selection."""
    lines = text.splitlines(keepends=True)
    if not lines:
        return 0, 0

    def absolute(offset: Offset) -> int:
        line = min(max(offset.y, 0), len(lines) - 1)
        column = min(max(offset.x, 0), len(lines[line].rstrip("\r\n")))
        return _line_start(text, line) + column

    start = Offset(0, 0) if selection.start is None else selection.start
    end = selection.end or Offset(len(lines) - 1, len(lines[-1].rstrip("\r\n")))
    return absolute(start), absolute(end)


def anchor_from_selection(block: DraftBlock, selection: Selection) -> DraftAnchor:
    """Turn one Textual selection into a block anchor with exact offsets."""
    quote = selection.extract(block.text)
    if not quote:
        return DraftAnchor(block.key)
    start, end = selection_offsets(block.text, selection)
    return DraftAnchor(block.key, quote, start, end)
