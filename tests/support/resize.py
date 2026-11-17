"""Headless resize matrix: record regions, content, selection, and scroll.

Every TUI surface ships one matrix run: mount once, then resize the headless
terminal through :data:`SIZES` and record the same facts at each size. One app
instance proves the live reflow, not a fresh mount per width.

The helpers here only read widget state. They never send keys, so a matrix run
cannot change the app's selection or scroll on its own.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

SIZES: tuple[tuple[int, int], ...] = ((40, 24), (80, 24), (120, 40), (160, 50))

# (x, y, width, height) in terminal cells.
Region = tuple[int, int, int, int]


def _cell_len(text: str) -> int:
    """Display cells for *text*; rich measures wide glyphs and emoji."""
    from rich.cells import cell_len

    return cell_len(text)


def region_of(widget: Any) -> Region | None:
    """The widget's painted rectangle, or ``None`` when it is not visible."""
    try:
        if not widget.display or not widget.visible:
            return None
        region = widget.region
    except Exception:  # noqa: BLE001 - a closing screen may race the walk
        return None
    if region.width <= 0 or region.height <= 0:
        return None
    return (region.x, region.y, region.width, region.height)


def content_width(widget: Any) -> int:
    """Widest source line of *widget* in cells.

    Only text widgets expose their source (``Static.content`` or the Markdown
    ``source``); containers report zero. Wrapping is measured from
    ``virtual_size`` in :class:`Part`, not from this raw source.
    """
    text = getattr(widget, "content", None)
    if not isinstance(text, str):
        text = getattr(widget, "source", None)
    if not isinstance(text, str):
        return 0
    return max((_cell_len(line) for line in text.splitlines()), default=0)


def _size_of(value: Any) -> tuple[int, int]:
    try:
        return (int(value.width), int(value.height))
    except Exception:  # noqa: BLE001 - older widget states may be partial
        return (0, 0)


def overlaps(first: Region, second: Region) -> bool:
    """True when two rectangles share at least one cell."""
    return not (
        first[0] + first[2] <= second[0]
        or second[0] + second[2] <= first[0]
        or first[1] + first[3] <= second[1]
        or second[1] + second[3] <= first[1]
    )


def inside(region: Region, size: tuple[int, int]) -> bool:
    """True when *region* fits inside a terminal of *size*."""
    x, y, width, height = region
    return x >= 0 and y >= 0 and x + width <= size[0] and y + height <= size[1]


@dataclass(frozen=True)
class Part:
    """One recorded widget: where it sits and how much content it holds."""

    name: str
    region: Region | None
    content: int
    virtual: tuple[int, int]
    content_size: tuple[int, int]
    widget: Any = field(default=None, compare=False, repr=False)

    @property
    def clipped(self) -> bool:
        """True when the widget's content is wider than the cells it paints."""
        if self.region is None:
            return False
        return self.virtual[0] > self.region[2]


@dataclass(frozen=True)
class Snapshot:
    """Everything one surface reports at one terminal size."""

    size: tuple[int, int]
    parts: dict[str, Part]
    selection: Any
    scroll: dict[str, tuple[int, int]]
    cursor: dict[str, int | None]

    def part(self, name: str) -> Part:
        """One recorded part by label."""
        return self.parts[name]

    def line(self) -> str:
        """One audit line: the size, regions, selection, and scroll."""
        regions = " ".join(f"{name}={part.region}" for name, part in sorted(self.parts.items()))
        scroll = " ".join(f"{name}={value}" for name, value in sorted(self.scroll.items()))
        return (
            f"{self.size[0]}x{self.size[1]} {regions}"
            f" selection={self.selection!r} scroll=[{scroll}]"
        )

    def assert_inside(self, case: Any) -> None:
        """Fail when a visible part paints outside the terminal."""
        for name, part in self.parts.items():
            if part.region is None:
                continue
            case.assertTrue(
                inside(part.region, self.size),
                f"{name} {part.region} leaves {self.size[0]}x{self.size[1]}",
            )

    def assert_no_overlap(self, case: Any, names: Iterable[str]) -> None:
        """Fail when two sibling parts share a cell."""
        selected = [(name, self.parts[name]) for name in names]
        for index, (first_name, first) in enumerate(selected):
            for second_name, second in selected[index + 1 :]:
                if first.region is None or second.region is None:
                    continue
                case.assertFalse(
                    overlaps(first.region, second.region),
                    f"{first_name} {first.region} overlaps "
                    f"{second_name} {second.region} at {self.size[0]}x{self.size[1]}",
                )

    def assert_unclipped(self, case: Any, names: Iterable[str]) -> None:
        """Fail when a part's content is wider than the cells it paints."""
        for name in names:
            part = self.parts[name]
            case.assertFalse(
                part.clipped,
                f"{name} content {part.virtual[0]} wider than "
                f"{part.region[2] if part.region else 0} at {self.size[0]}x{self.size[1]}",
            )


@dataclass
class ResizeMatrix:
    """The recorded snapshots for one surface, in :data:`SIZES` order."""

    name: str
    snapshots: list[Snapshot] = field(default_factory=list)

    def at(self, size: tuple[int, int]) -> Snapshot:
        """The snapshot recorded at exactly *size*."""
        for snapshot in self.snapshots:
            if snapshot.size == size:
                return snapshot
        raise KeyError(f"{self.name}: no snapshot at {size[0]}x{size[1]}")

    def sizes(self) -> tuple[tuple[int, int], ...]:
        """The sizes recorded, in walk order."""
        return tuple(snapshot.size for snapshot in self.snapshots)

    def summary(self) -> str:
        """A multi-line report for the audit note and failure messages."""
        return "\n".join([self.name, *(snapshot.line() for snapshot in self.snapshots)])

    async def walk(
        self,
        pilot: Any,
        *,
        parts: dict[str, str],
        selection: Any = None,
        scrolls: Iterable[str] = (),
        cursors: Iterable[str] = (),
    ) -> ResizeMatrix:
        """Resize through every size and record *parts* after each layout.

        *parts* maps a label to a CSS selector on the screen. *selection* is a
        callable (read after each resize) or a plain value. *scrolls* and
        *cursors* list selectors whose scroll offset and highlighted index are
        recorded too.
        """
        screen = pilot.app.screen
        for width, height in SIZES:
            await pilot.resize_terminal(width, height)
            await pilot.pause()
            await pilot.pause()
            self.snapshots.append(
                record(
                    screen,
                    (width, height),
                    parts,
                    selection=selection,
                    scrolls=scrolls,
                    cursors=cursors,
                )
            )
        return self


def record(
    screen: Any,
    size: tuple[int, int],
    parts: dict[str, str],
    *,
    selection: Any = None,
    scrolls: Iterable[str] = (),
    cursors: Iterable[str] = (),
) -> Snapshot:
    """Read the current widget state into one :class:`Snapshot`."""
    recorded: dict[str, Part] = {}
    for name, selector in parts.items():
        widget = _query(screen, selector)
        recorded[name] = Part(
            name=name,
            region=region_of(widget) if widget is not None else None,
            content=content_width(widget) if widget is not None else 0,
            virtual=_size_of(widget.virtual_size) if widget is not None else (0, 0),
            content_size=_size_of(widget.content_size) if widget is not None else (0, 0),
            widget=widget,
        )
    scroll: dict[str, tuple[int, int]] = {}
    for selector in scrolls:
        widget = _query(screen, selector)
        if widget is None:
            continue
        try:
            scroll[selector] = (int(widget.scroll_y), int(widget.max_scroll_y))
        except Exception:  # noqa: BLE001 - not every widget scrolls
            continue
    cursor: dict[str, int | None] = {}
    for selector in cursors:
        widget = _query(screen, selector)
        if widget is None:
            continue
        try:
            cursor[selector] = widget.highlighted
        except Exception:  # noqa: BLE001 - not every widget highlights rows
            continue
    if callable(selection):
        selection = selection()
    return Snapshot(
        size=size,
        parts=recorded,
        selection=selection,
        scroll=scroll,
        cursor=cursor,
    )


def _query(screen: Any, selector: str) -> Any:
    """One optional widget, tolerating a screen that is closing."""
    try:
        return screen.query_one(selector)
    except Exception:  # noqa: BLE001 - absent widgets are a normal state
        return None


async def settle(pilot: Any) -> None:
    """Let a resize, its reflow, and ``call_after_refresh`` work all land."""
    await pilot.pause()
    await pilot.pause()
