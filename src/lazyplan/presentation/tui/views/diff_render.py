"""Render commit diffs as scannable unified Rich-markup rows."""

from __future__ import annotations

from lazyplan.services.source import DiffFile, DiffLine

from .diff_common import (
    _code_spans,
    _context_row,
    _emphasis,
    _file_bar,
    _fold_context,
    _hunk_bar,
    _line_gutter,
    _plain_width,
    _row,
    _truncate_spans,
    _wrap_spans,
)
from .diff_common import diff_counts as diff_counts
from .diff_style import DiffOptions as DiffOptions
from .diff_style import DiffPalette as DiffPalette

MIN_CODE_WIDTH = 10


def _render_line(
    line: DiffLine,
    index: int,
    path: str,
    width: int,
    digits: int,
    palette: DiffPalette,
    emphasis: dict[int, list[tuple[int, int]]],
    options: DiffOptions,
) -> list[str]:
    """Render one add, remove, or context line."""
    is_add = line.kind == "add"
    is_remove = line.kind == "remove"
    if is_add:
        fg, background, marker, emphasis_style = (
            palette.add,
            palette.add_bg,
            "+",
            palette.emphasis_add,
        )
    elif is_remove:
        fg, background, marker, emphasis_style = (
            palette.remove,
            palette.remove_bg,
            "-",
            palette.emphasis_remove,
        )
    else:
        fg, background, marker, emphasis_style = palette.context, "", "·", palette.context
    gutter = _line_gutter(line, digits)
    prefix = f"{gutter} {marker} "
    spans = _code_spans(
        line,
        path,
        fg,
        palette,
        emphasis.get(index, []),
        emphasis_style,
    )
    code_width = max(MIN_CODE_WIDTH, width - _plain_width(prefix))
    rows: list[str] = []
    if options.wrap:
        for part, chunk in enumerate(_wrap_spans(spans, code_width)):
            row_prefix = prefix if part == 0 else f"{' ' * (digits * 2 + 1)} ↳ "
            rows.append(_row(row_prefix, chunk, width, fg, background))
    else:
        rows.append(
            _row(
                prefix,
                _truncate_spans(spans, code_width, fg),
                width,
                fg,
                background,
            )
        )
    return rows


def render_file(
    file: DiffFile,
    width: int,
    palette: DiffPalette | None = None,
    options: DiffOptions | None = None,
) -> list[str]:
    """Render one file section: a header bar, hunks, and rows."""
    palette = palette or DiffPalette()
    options = options or DiffOptions()
    width = max(20, width)
    rows = [_file_bar(file, width, palette)]
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
        for original, item in _fold_context(hunk.lines, options):
            if isinstance(item, int):
                rows.append(_context_row(item, palette))
            else:
                rows.extend(
                    _render_line(
                        item,
                        original,
                        file.path,
                        width,
                        digits,
                        palette,
                        emphasis,
                        options,
                    )
                )
    return rows


def render_unified(
    files: tuple[DiffFile, ...],
    width: int,
    palette: DiffPalette | None = None,
    options: DiffOptions | None = None,
) -> list[str]:
    """Render commit files as unified diff rows."""
    if not files:
        return ["[dim]no textual changes[/]"]
    rows: list[str] = []
    for position, file in enumerate(files):
        if position:
            rows.append("")
        rows.extend(render_file(file, width, palette, options))
    return rows
