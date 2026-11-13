"""Palette and display switches shared by the unified and split renderers."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

FOLD_AFTER = 6
FOLD_KEEP = 3

ACTION_GLYPH = {"add": "+", "remove": "-", "change": "~", "move": "→"}
ACTION_SLOT = {
    "add": "add",
    "remove": "remove",
    "change": "change",
    "move": "move",
}

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


@dataclass(frozen=True)
class DiffPalette:
    """Colours and syntax styles for one theme."""

    add: str = "#a6e3a1"
    remove: str = "#f38ba8"
    add_bg: str = "#1e3a2a"
    remove_bg: str = "#3a1e2a"
    hunk: str = "#89b4fa"
    hunk_bg: str = "#1e2a3a"
    change: str = "#f9e2af"
    move: str = "#94e2d5"
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
            change=theme.get("lp-diff-change", cls.change),
            move=theme.get("lp-diff-move", cls.move),
            file=theme.get("lp-accent", cls.file),
            file_bg=theme.get("lp-surface-raised", cls.file_bg),
            gutter=theme.get("lp-text-faint", cls.gutter),
            context=theme.get("lp-text-muted", cls.context),
            emphasis_add=(
                f"bold {theme.get('lp-diff-add', cls.add)} "
                f"on {theme.get('lp-diff-emphasis-add', '#2f5f3f')}"
            ),
            emphasis_remove=(
                f"bold {theme.get('lp-diff-remove', cls.remove)} "
                f"on {theme.get('lp-diff-emphasis-remove', '#5f2f3f')}"
            ),
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


def palette_from_theme(theme: Mapping[str, object]) -> DiffPalette:
    """Build a diff palette from an app's theme-variable mapping."""
    return DiffPalette.from_theme({name: str(value) for name, value in theme.items()})
