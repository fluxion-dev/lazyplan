"""Render commit diffs as scannable Rich-markup rows.

The renderer is pure: parse the patch once, pass a width and palette, and get
back one markup string per row. It owns file bars, gutters, tints, folded
context, changed-word emphasis, and wrapping so every screen paints the same
diff language.
"""

from __future__ import annotations

import difflib
from collections.abc import Mapping
from dataclasses import dataclass, field

from rich.cells import cell_len

from lazyplan.services.source import DiffFile, DiffHunk, DiffLine

from ...shared.design import escape_markup
from .highlight import highlight_line

FOLD_AFTER = 6
FOLD_KEEP = 3
MIN_CODE_WIDTH = 10

_STATUS_STYLE = {
    "add": ("A", "add"),
    "delete": ("D", "remove"),
    "rename": ("R", "hunk"),
    "modify": ("M", "hunk"),
}


@dataclass(frozen=True)
class DiffPalette:
    """Colours and syntax styles for one theme."""

    add: str = "#a6e3a1"
    remove: str = "#f38ba8"
    add_bg: str = "#1e3a2a"
    remove_bg: str = "#3a1e2a"
    hunk: str = "#89b4fa"
    hunk_bg: str = "#1e2a3a"
    file: str = "#b4befe"
    file_bg: str = "#2a2a3e"
    gutter: str = "#6c7086"
    context: str = "#a6adc8"
    emphasis_add: str = "bold #a6e3a1 on #2f5f3f"
    emphasis_remove: str = "bold #f38ba8 on #5f2f3f"
    syntax: Mapping[str, str] = field(default_factory=dict)

    @classmethod
    def from_theme(cls, theme: Mapping[str, str]) -> DiffPalette:
        """Build a palette from ``lp-*`` theme variables."""
        return cls(
            add=theme.get("lp-diff-add", cls.add),
            remove=theme.get("lp-diff-remove", cls.remove),
            add_bg=theme.get("lp-diff-add-bg", cls.add_bg),
            remove_bg=theme.get("lp-diff-remove-bg", cls.remove_bg),
            hunk=theme.get("lp-diff-hunk", cls.hunk),
            hunk_bg=theme.get("lp-diff-hunk-bg", cls.hunk_bg),
            file=theme.get("lp-accent", cls.file),
            file_bg=theme.get("lp-surface-raised", cls.file_bg),
            gutter=theme.get("lp-text-faint", cls.gutter),
            context=theme.get("lp-text-muted", cls.context),
            syntax={
                kind: theme.get(f"lp-syntax-{kind}", default)
                for kind, default in _DEFAULT_SYNTAX.items()
            },
        )


@dataclass(frozen=True)
class DiffOptions:
    """Display switches for one rendered diff."""

    fold: bool = True
    wrap: bool = True
    fold_after: int = FOLD_AFTER
    fold_keep: int = FOLD_KEEP


_DEFAULT_SYNTAX: dict[str, str] = {
    "comment": "italic #6c7086",
    "keyword": "bold #cba6f7",
    "string": "#a6e3a1",
    "number": "#fab387",
    "function": "#89b4fa",
    "class": "#f9e2af",
    "builtin": "#f5c2e7",
    "decorator": "#f5c2e7",
    "operator": "#89dceb",
    "punct": "#bac2de",
    "text": "",
}


def diff_counts(item: DiffFile) -> tuple[int, int]:
    """Added and removed line counts for one file."""
    added = sum(1 for hunk in item.hunks for line in hunk.lines if line.kind == "add")
    removed = sum(1 for hunk in item.hunks for line in hunk.lines if line.kind == "remove")
    return added, removed


def _bg(style: str, background: str) -> str:
    """Combine a foreground style with a row background."""
    return f"{style} on {background}" if background else style


def _plain_width(text: str) -> int:
    """Display width of plain text, including wide characters."""
    return cell_len(text.expandtabs(4))


def _pad(text: str, width: int) -> str:
    """Spaces needed to reach *width* cells."""
    return " " * max(0, width - _plain_width(text))


def _truncate_plain(text: str, width: int) -> str:
    """Trim plain text to *width* cells, adding an ellipsis when cut."""
    if width <= 0:
        return ""
    if _plain_width(text) <= width:
        return text
    out = ""
    for char in text:
        if _plain_width(out + char) > width - 1:
            break
        out += char
    return f"{out.rstrip()}…"


def _status(file: DiffFile) -> tuple[str, str]:
    """Status letter and palette slot for one file."""
    return _STATUS_STYLE.get(file.status, ("M", "hunk"))


def _file_name(file: DiffFile) -> str:
    """Display path, showing the rename source when there is one."""
    if file.status == "rename" and file.old_path:
        return f"{file.old_path} → {file.path}"
    return file.path


def _file_bar(file: DiffFile, width: int, palette: DiffPalette) -> str:
    """One full-width file header bar."""
    letter, slot = _status(file)
    color = getattr(palette, slot)
    added, removed = diff_counts(file)
    right = "binary" if file.binary else f"+{added} -{removed}"
    prefix = f" {letter} "
    available = max(1, width - _plain_width(prefix) - _plain_width(right) - 1)
    name = _truncate_plain(_file_name(file), available)
    path = escape_markup(name)
    head = f"{letter} {name}"
    gap = _pad(f" {head} {right}", width)
    style = _bg(f"bold {color}", palette.file_bg)
    count = _bg("dim" if not file.binary else "yellow", palette.file_bg)
    return f"[{style}] {letter} {path}[/][{count}] {right}{gap}[/]"


def _hunk_bar(hunk: DiffHunk, width: int, palette: DiffPalette) -> str:
    """One hunk header bar with its section context."""
    text = hunk.header
    text = _truncate_plain(text, max(1, width - 1))
    style = _bg(f"bold {palette.hunk}", palette.hunk_bg)
    return f"[{style}] {escape_markup(text)}{_pad(text, width - 1)}[/]"


def _line_gutter(line: DiffLine, digits: int) -> str:
    """Old and new line numbers, padded to *digits*."""
    old = f"{line.old_no:>{digits}}" if line.old_no is not None else " " * digits
    new = f"{line.new_no:>{digits}}" if line.new_no is not None else " " * digits
    return f"{old} {new}"


def _word_ranges(old: str, new: str) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    """Changed character spans for one removed/added pair."""
    old_ranges: list[tuple[int, int]] = []
    new_ranges: list[tuple[int, int]] = []
    matcher = difflib.SequenceMatcher(None, old, new, autojunk=False)
    for tag, old_start, old_end, new_start, new_end in matcher.get_opcodes():
        if tag == "equal":
            continue
        if old_start != old_end:
            old_ranges.append((old_start, old_end))
        if new_start != new_end:
            new_ranges.append((new_start, new_end))
    return old_ranges, new_ranges


def _emphasis(lines: tuple[DiffLine, ...]) -> dict[int, list[tuple[int, int]]]:
    """Changed-word spans keyed by line index."""
    ranges: dict[int, list[tuple[int, int]]] = {}
    index = 0
    while index < len(lines):
        if lines[index].kind != "remove":
            index += 1
            continue
        remove_end = index
        while remove_end < len(lines) and lines[remove_end].kind == "remove":
            remove_end += 1
        add_end = remove_end
        while add_end < len(lines) and lines[add_end].kind == "add":
            add_end += 1
        pairs = min(remove_end - index, add_end - remove_end)
        for offset in range(pairs):
            old_ranges, new_ranges = _word_ranges(
                lines[index + offset].text.expandtabs(4),
                lines[remove_end + offset].text.expandtabs(4),
            )
            ranges[index + offset] = old_ranges
            ranges[remove_end + offset] = new_ranges
        index = add_end if add_end > index else index + 1
    return ranges


def _styled(kind: str, text: str, fg: str, palette: DiffPalette) -> tuple[str, str]:
    """One span with its syntax style, falling back to the row colour."""
    syntax = palette.syntax.get(kind, "")
    return (syntax or fg, text)


def _split_emphasis(
    spans: list[tuple[str, str]],
    ranges: list[tuple[int, int]],
    emphasis: str,
) -> list[tuple[str, str]]:
    """Split spans so changed character ranges carry *emphasis*."""
    if not ranges:
        return spans
    out: list[tuple[str, str]] = []
    position = 0
    for style, text in spans:
        start = position
        end = position + len(text)
        position = end
        cuts = {start, end}
        for low, high in ranges:
            if low < end and high > start:
                cuts.add(max(low, start))
                cuts.add(min(high, end))
        points = sorted(cuts)
        for low, high in zip(points, points[1:], strict=False):
            if low == high:
                continue
            changed = any(low >= a and high <= b for a, b in ranges)
            out.append((emphasis if changed else style, text[low - start : high - start]))
    return out


def _append_span(spans: list[tuple[str, str]], style: str, char: str) -> None:
    """Append one character, merging runs with the same style."""
    if spans and spans[-1][0] == style:
        spans[-1] = (style, spans[-1][1] + char)
    else:
        spans.append((style, char))


def _wrap_spans(
    spans: list[tuple[str, str]],
    width: int,
) -> list[list[tuple[str, str]]]:
    """Split styled spans into display-width rows."""
    rows: list[list[tuple[str, str]]] = []
    current: list[tuple[str, str]] = []
    used = 0
    for style, text in spans:
        for char in text:
            size = cell_len(char)
            if used + size > width and used:
                rows.append(current)
                current = []
                used = 0
            _append_span(current, style, char)
            used += size
    if current or not rows:
        rows.append(current)
    return rows


def _truncate_spans(
    spans: list[tuple[str, str]],
    width: int,
    fallback: str,
) -> list[tuple[str, str]]:
    """Trim styled spans to *width* cells and mark the cut."""
    rows = _wrap_spans(spans, width)
    if len(rows) == 1:
        return rows[0]
    first = rows[0][:]
    _append_span(first, fallback or "dim", "…")
    return first


def _code_spans(
    line: DiffLine,
    path: str,
    fg: str,
    palette: DiffPalette,
    ranges: list[tuple[int, int]],
    emphasis: str,
) -> list[tuple[str, str]]:
    """Syntax and emphasis spans for one code line."""
    text = line.text.expandtabs(4)
    spans = [_styled(kind, value, fg, palette) for kind, value in highlight_line(path, text)]
    return _split_emphasis(spans, ranges, emphasis)


def _row(
    prefix: str,
    spans: list[tuple[str, str]],
    width: int,
    fg: str,
    background: str,
) -> str:
    """One diff row with a tinted background and right padding."""
    body = "".join(f"[{style}]{escape_markup(text)}[/]" for style, text in spans)
    plain = prefix + "".join(text for _style, text in spans)
    gap = " " * max(0, width - _plain_width(plain))
    style = _bg(fg, background)
    return f"[{style}]{escape_markup(prefix)}[/]{body}[{style}]{gap}[/]"


def _fold_context(
    lines: tuple[DiffLine, ...],
    options: DiffOptions,
) -> list[tuple[int, DiffLine | int]]:
    """Replace long unchanged runs with a count row, keeping source indexes."""
    if not options.fold:
        return list(enumerate(lines))
    out: list[tuple[int, DiffLine | int]] = []
    index = 0
    while index < len(lines):
        if lines[index].kind != "context":
            out.append((index, lines[index]))
            index += 1
            continue
        end = index
        while end < len(lines) and lines[end].kind == "context":
            end += 1
        run = end - index
        if run > options.fold_after:
            for offset in range(options.fold_keep):
                out.append((index + offset, lines[index + offset]))
            out.append((-1, run - options.fold_keep * 2))
            for offset in range(run - options.fold_keep, run):
                out.append((index + offset, lines[index + offset]))
        else:
            for offset in range(run):
                out.append((index + offset, lines[index + offset]))
        index = end
    return out


def _context_row(hidden: int, palette: DiffPalette) -> str:
    """One collapsed-context row."""
    label = f"⋯ {hidden} unchanged lines"
    return f"[{_bg('dim ' + palette.gutter, '')}]{escape_markup(label)}[/]"


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
