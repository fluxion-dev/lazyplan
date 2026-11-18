"""Selectable single-cell icon palettes for the CLI, setup, and TUI.

One palette names every glyph a surface draws, so a choice changes the whole
icon language together: status marks, row kinds, preview sections, checkout
state, and the setup wizard. The Unicode palettes keep each glyph in one
terminal cell so rows, breadcrumbs, and the git pane stay aligned; ``ascii``
trades width for compatibility on terminals without those glyphs.

Selection precedence is ``LAZYPLAN_ICONS``, then the saved setup choice, then
``classic``. ``apply_icons`` updates the shared maps in place, so modules that
imported ``STATUS_GLYPH`` or ``KIND_ICON`` draw the new palette on the next
render without re-importing.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

ENV_VAR = "LAZYPLAN_ICONS"
DEFAULT_ICONS = "classic"


@dataclass(frozen=True)
class IconPalette:
    """One complete icon language; every map has the same keys."""

    name: str
    label: str
    icons: Mapping[str, str]
    status: Mapping[str, str]
    kind: Mapping[str, str]
    section: Mapping[str, str]
    state: Mapping[str, str]


_ICONS = "setup check circle arrow warn dot".split()
_STATUS = "todo doing done".split()
_KIND = "plan milestone task".split()
_SECTION = (
    "why",
    "what",
    "details",
    "next",
    "acceptance",
    "notes",
    "comments",
    "source",
    "git",
    "repos",
    "commits",
    "pulls",
    "milestones",
    "tasks",
)
_STATE = "clean dirty detached".split()


def _palette(
    name: str,
    label: str,
    *,
    icons: tuple[str, ...],
    status: tuple[str, ...],
    kind: tuple[str, ...],
    section: tuple[str, ...],
    state: tuple[str, ...],
) -> IconPalette:
    """Build one palette; ``zip(strict=True)`` rejects a short map."""
    return IconPalette(
        name=name,
        label=label,
        icons=dict(zip(_ICONS, icons, strict=True)),
        status=dict(zip(_STATUS, status, strict=True)),
        kind=dict(zip(_KIND, kind, strict=True)),
        section=dict(zip(_SECTION, section, strict=True)),
        state=dict(zip(_STATE, state, strict=True)),
    )


CLASSIC = _palette(
    "classic",
    "Classic",
    icons=("◆", "✓", "○", "→", "⚠", "·"),
    status=("○", "◐", "●"),
    kind=("◈", "◇", "▹"),
    section=(
        "◎",
        "◇",
        "◇",
        "▸",
        "✓",
        "✎",
        "✎",
        "⌁",
        "⎇",
        "⌂",
        "◆",
        "⇄",
        "◇",
        "▹",
    ),
    state=("○", "●", "⊘"),
)

ORBIT = _palette(
    "orbit",
    "Orbit",
    icons=("◉", "✓", "○", "→", "⚠", "·"),
    status=("○", "◑", "●"),
    kind=("◉", "○", "∙"),
    section=(
        "◉",
        "○",
        "○",
        "›",
        "✓",
        "✎",
        "✎",
        "⌁",
        "⑂",
        "⌂",
        "◉",
        "⇄",
        "○",
        "∙",
    ),
    state=("○", "◉", "⊘"),
)

BLOCKS = _palette(
    "blocks",
    "Blocks",
    icons=("■", "✓", "□", "▸", "▲", "·"),
    status=("□", "◪", "■"),
    kind=("◆", "◇", "▸"),
    section=(
        "◈",
        "◇",
        "◇",
        "▸",
        "✓",
        "✎",
        "✎",
        "⌗",
        "⎇",
        "⌂",
        "◆",
        "⇄",
        "◇",
        "▸",
    ),
    state=("□", "■", "⊠"),
)

MARKS = _palette(
    "marks",
    "Marks",
    icons=("✦", "✓", "○", "→", "!", "·"),
    status=("·", "▸", "✓"),
    kind=("✦", "✧", "›"),
    section=(
        "✦",
        "✧",
        "✧",
        "→",
        "✓",
        "✎",
        "✎",
        "⌁",
        "⑂",
        "⌂",
        "✦",
        "⇄",
        "✧",
        "›",
    ),
    state=("○", "●", "⊘"),
)

ASCII = _palette(
    "ascii",
    "ASCII",
    icons=("*", "[x]", "[ ]", "->", "!", "-"),
    status=(".", "+", "x"),
    kind=("P", "M", "T"),
    section=("?", ":", ":", ">", "+", "*", "*", "@", "&", "#", "*", "<>", "M", "T"),
    state=(".", "*", "!"),
)

ICON_PALETTES: tuple[IconPalette, ...] = (CLASSIC, ORBIT, BLOCKS, MARKS, ASCII)
ICON_NAMES: tuple[str, ...] = tuple(palette.name for palette in ICON_PALETTES)
DEFAULT_PALETTE = CLASSIC
PALETTES: dict[str, IconPalette] = {palette.name: palette for palette in ICON_PALETTES}

_ALIASES = {
    "classic": "classic",
    "default": "classic",
    "geometric": "classic",
    "original": "classic",
    "orbit": "orbit",
    "circles": "orbit",
    "round": "orbit",
    "dots": "orbit",
    "blocks": "blocks",
    "square": "blocks",
    "squares": "blocks",
    "angular": "blocks",
    "marks": "marks",
    "ticks": "marks",
    "editorial": "marks",
    "ascii": "ascii",
    "plain": "ascii",
    "compat": "ascii",
    "safe": "ascii",
}

_active = DEFAULT_ICONS


def resolve_icons(raw: str | None) -> str:
    """Canonical palette name for a stored value, or an empty string."""
    return _ALIASES.get((raw or "").strip().lower(), "")


def icon_palette(name: str | None) -> IconPalette:
    """The named palette, falling back to the default."""
    return PALETTES.get(resolve_icons(name), DEFAULT_PALETTE)


def choose_icons(remembered: str = "", explicit: str | None = None) -> str:
    """Resolve a palette: ``LAZYPLAN_ICONS`` first, then memory, then default."""
    candidates = (
        os.environ.get(ENV_VAR, ""),
        remembered if explicit is None else explicit,
    )
    for candidate in candidates:
        name = resolve_icons(candidate)
        if name:
            return name
    return DEFAULT_ICONS


def remembered_icons(home: Path | None = None) -> str:
    """The palette the last cycle or wizard apply saved."""
    from ...setup.state import load_state

    return load_state(home).icons


def remember_icons(name: str, home: Path | None = None) -> str:
    """Save the palette the screen shows so the next launch opens with it."""
    from ...setup.state import load_state, save_state

    state = load_state(home)
    state.icons = resolve_icons(name) or DEFAULT_ICONS
    save_state(state, home)
    return state.icons


def next_icons(current: str) -> str:
    """Return the next palette in registration order."""
    try:
        index = ICON_NAMES.index(current)
    except ValueError:
        return ICON_NAMES[0]
    return ICON_NAMES[(index + 1) % len(ICON_NAMES)]


def active_icons() -> str:
    """The palette the shared maps currently draw."""
    return _active


def apply_icons(name: str) -> str:
    """Point the shared glyph maps at one palette and return its name."""
    selected = resolve_icons(name) or DEFAULT_ICONS
    palette = PALETTES[selected]
    from . import text, tokens

    _replace(text.STATUS_GLYPH, palette.status)
    _replace(tokens.ICONS, palette.icons)
    _replace(tokens.KIND_ICON, palette.kind)
    _replace(tokens.SECTION_ICON, palette.section)
    _replace(tokens.STATE_ICON, palette.state)
    global _active
    _active = selected
    return selected


def select_icons(remembered: str = "") -> str:
    """Resolve and apply the palette for this launch."""
    return apply_icons(choose_icons(remembered))


def _replace(target: dict[str, str], source: Mapping[str, str]) -> None:
    """Update a shared map in place so existing imports see the change."""
    target.clear()
    target.update(source)
