"""Render commit diffs as paired old/new columns."""

from __future__ import annotations

from dataclasses import dataclass

from lazyplan.services.source import DiffFile, DiffLine

from .diff_render import (
    _code_spans,
    _context_row,
    _emphasis,
    _file_bar,
    _fold_context,
    _hunk_bar,
    _plain_width,
    _row,
    _truncate_spans,
    _wrap_spans,
)
from .diff_style import DiffOptions, DiffPalette

MIN_SPLIT_WIDTH = 76
MIN_SPLIT_COLUMN = 24


@dataclass(frozen=True)
class SplitResult:
    """A side-by-side render, or the reason it cannot fit."""

    available: bool = True
    rows: tuple[str, ...] = ()
    detail: str = ""


@dataclass(frozen=True)
class _Pair:
    """One left/right row in a split diff."""

    left: DiffLine | None = None
    right: DiffLine | None = None
    left_index: int = -1
    right_index: int = -1
    hidden: int = 0


def _pairs(
    lines: tuple[DiffLine, ...],
    options: DiffOptions,
) -> list[_Pair]:
    """Pair removed, added, context, and folded rows for two columns."""
    items = _fold_context(lines, options)
    out: list[_Pair] = []
    index = 0
    while index < len(items):
        position, item = items[index]
        if isinstance(item, int):
            out.append(_Pair(hidden=item))
            index += 1
            continue
        if item.kind == "context":
            out.append(_Pair(item, item, position, position))
            index += 1
            continue
        if item.kind == "remove":
            removes: list[tuple[int, DiffLine]] = []
            adds: list[tuple[int, DiffLine]] = []
            while index < len(items):
                place, candidate = items[index]
                if not isinstance(candidate, DiffLine) or candidate.kind != "remove":
                    break
                removes.append((place, candidate))
                index += 1
            while index < len(items):
                place, candidate = items[index]
                if not isinstance(candidate, DiffLine) or candidate.kind != "add":
                    break
                adds.append((place, candidate))
                index += 1
            for offset in range(max(len(removes), len(adds))):
                left = removes[offset] if offset < len(removes) else (-1, None)
                right = adds[offset] if offset < len(adds) else (-1, None)
                out.append(_Pair(left[1], right[1], left[0], right[0]))
            continue
        if item.kind == "add":
            out.append(_Pair(None, item, -1, position))
        else:
            out.append(_Pair(item, None, position, -1))
        index += 1
    return out


def _side(
    line: DiffLine | None,
    position: int,
    path: str,
    width: int,
    digits: int,
    palette: DiffPalette,
    emphasis: dict[int, list[tuple[int, int]]],
    options: DiffOptions,
    side: str,
) -> list[str]:
    """Render one side of a split row at *width* cells."""
    width = max(1, width)
    if line is None:
        return [" " * width]
    if line.kind == "meta":
        style = f"dim {palette.gutter}".strip()
        return [_row("", [(style, line.text)], width, palette.context, "")]
    is_add = line.kind == "add"
    is_remove = line.kind == "remove"
    if is_add:
        fg, background, marker = palette.add, palette.add_bg, "+"
        emphasis_style = palette.emphasis_add
    elif is_remove:
        fg, background, marker = palette.remove, palette.remove_bg, "-"
        emphasis_style = palette.emphasis_remove
    else:
        fg, background, marker = palette.context, "", "·"
        emphasis_style = palette.context
    number = line.old_no if side == "left" else line.new_no
    label = f"{number:>{digits}}" if number is not None else " " * digits
    prefix = f"{label} {marker} "
    spans = _code_spans(
        line,
        path,
        fg,
        palette,
        emphasis.get(position, []),
        emphasis_style,
    )
    code_width = max(4, width - _plain_width(prefix))
    if not options.wrap:
        return [_row(prefix, _truncate_spans(spans, code_width, fg), width, fg, background)]
    rows: list[str] = []
    for part, chunk in enumerate(_wrap_spans(spans, code_width)):
        row_prefix = prefix if part == 0 else f"{' ' * (digits + 1)}↳ "
        rows.append(_row(row_prefix, chunk, width, fg, background))
    return rows


def _pair_rows(
    pair: _Pair,
    path: str,
    width: int,
    digits: int,
    palette: DiffPalette,
    emphasis: dict[int, list[tuple[int, int]]],
    options: DiffOptions,
) -> list[str]:
    """Render one split pair, padding the shorter side."""
    if pair.hidden:
        return [_context_row(pair.hidden, palette)]
    left_width = max(MIN_SPLIT_COLUMN, (width - 1) // 2)
    right_width = max(MIN_SPLIT_COLUMN, width - left_width - 1)
    left = _side(
        pair.left,
        pair.left_index,
        path,
        left_width,
        digits,
        palette,
        emphasis,
        options,
        "left",
    )
    right = _side(
        pair.right,
        pair.right_index,
        path,
        right_width,
        digits,
        palette,
        emphasis,
        options,
        "right",
    )
    separator = f"[{palette.gutter}]│[/]" if palette.gutter else "│"
    rows: list[str] = []
    for index in range(max(len(left), len(right))):
        left_row = left[index] if index < len(left) else " " * left_width
        right_row = right[index] if index < len(right) else " " * right_width
        rows.append(f"{left_row}{separator}{right_row}")
    return rows


def render_split(
    files: tuple[DiffFile, ...],
    width: int,
    palette: DiffPalette | None = None,
    options: DiffOptions | None = None,
) -> SplitResult:
    """Render commit files as paired old/new columns."""
    palette = palette or DiffPalette()
    options = options or DiffOptions()
    if width < MIN_SPLIT_WIDTH:
        return SplitResult(
            available=False,
            detail=f"side-by-side needs {MIN_SPLIT_WIDTH} columns; the pane has {width}",
        )
    if not files:
        return SplitResult(rows=("[dim]no textual changes[/]",))
    rows: list[str] = []
    for position, file in enumerate(files):
        if position:
            rows.append("")
        rows.append(_file_bar(file, width, palette))
        for hunk in file.hunks:
            rows.append(_hunk_bar(hunk, width, palette))
            numbers = [
                number
                for line in hunk.lines
                for number in (line.old_no, line.new_no)
                if number is not None
            ]
            digits = max(3, len(str(max(numbers))) if numbers else 1)
            emphasis = _emphasis(hunk.lines)
            for pair in _pairs(hunk.lines, options):
                rows.extend(
                    _pair_rows(
                        pair,
                        file.path,
                        width,
                        digits,
                        palette,
                        emphasis,
                        options,
                    )
                )
    return SplitResult(rows=tuple(rows))
