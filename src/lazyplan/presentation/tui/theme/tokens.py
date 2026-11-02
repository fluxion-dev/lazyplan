"""Semantic colour tokens for the lazyplan themes.

The palette follows Catppuccin: Mocha for the dark theme, Latte for the
light theme, and an OLED-black variant of Mocha for ``void``. Every theme
carries the same keys, so the stylesheets and chart adapters never guess.
"""

from __future__ import annotations

DARK_TOKENS: dict[str, str] = {
    "lp-surface": "#1e1e2e",
    "lp-surface-alt": "#181825",
    "lp-surface-raised": "#313244",
    "lp-surface-overlay": "#11111b",
    "lp-border": "#45475a",
    "lp-border-muted": "#313244",
    "lp-border-focus": "#89b4fa",
    "lp-text-muted": "#a6adc8",
    "lp-text-faint": "#6c7086",
    "lp-accent": "#b4befe",
    "lp-accent-muted": "#89b4fa",
    "lp-focus": "#89b4fa",
    "lp-cursor": "#3e4869",
    "lp-modal-bg": "#181825",
    "lp-overlay": "black 50%",
    "lp-status-todo": "#7f849c",
    "lp-status-doing": "#f9e2af",
    "lp-status-done": "#a6e3a1",
    "lp-status-blocked": "#f38ba8",
    "lp-chip-bg": "#313244",
    "lp-chip-fg": "#cdd6f4",
    "lp-git-clean": "#a6e3a1",
    "lp-git-dirty": "#f38ba8",
    "lp-chart-bar": "#a6e3a1",
    "lp-chart-axis": "#7f849c",
    "lp-chart-label": "#cdd6f4",
    "lp-chart-lane-1": "#a6e3a1",
    "lp-chart-lane-2": "#89b4fa",
    "lp-chart-lane-3": "#f9e2af",
    "lp-chart-lane-4": "#cba6f7",
    "lp-chart-lane-5": "#f38ba8",
    "lp-chart-lane-6": "#94e2d5",
    "lp-diff-add": "#a6e3a1",
    "lp-diff-remove": "#f38ba8",
}

LIGHT_TOKENS: dict[str, str] = {
    "lp-surface": "#eff1f5",
    "lp-surface-alt": "#e6e9ef",
    "lp-surface-raised": "#ccd0da",
    "lp-surface-overlay": "#dce0e8",
    "lp-border": "#bcc0cc",
    "lp-border-muted": "#ccd0da",
    "lp-border-focus": "#1e66f5",
    "lp-text-muted": "#6c6f85",
    "lp-text-faint": "#8c8fa1",
    "lp-accent": "#7287fd",
    "lp-accent-muted": "#1e66f5",
    "lp-focus": "#1e66f5",
    "lp-cursor": "#dce0e8",
    "lp-modal-bg": "#eff1f5",
    "lp-overlay": "black 30%",
    "lp-status-todo": "#8c8fa1",
    "lp-status-doing": "#df8e1d",
    "lp-status-done": "#40a02b",
    "lp-status-blocked": "#d20f39",
    "lp-chip-bg": "#ccd0da",
    "lp-chip-fg": "#4c4f69",
    "lp-git-clean": "#40a02b",
    "lp-git-dirty": "#d20f39",
    "lp-chart-bar": "#40a02b",
    "lp-chart-axis": "#8c8fa1",
    "lp-chart-label": "#4c4f69",
    "lp-chart-lane-1": "#40a02b",
    "lp-chart-lane-2": "#1e66f5",
    "lp-chart-lane-3": "#df8e1d",
    "lp-chart-lane-4": "#8839ef",
    "lp-chart-lane-5": "#d20f39",
    "lp-chart-lane-6": "#179299",
    "lp-diff-add": "#40a02b",
    "lp-diff-remove": "#d20f39",
}

VOID_TOKENS: dict[str, str] = {
    **DARK_TOKENS,
    "lp-surface": "#000000",
    "lp-surface-alt": "#070709",
    "lp-surface-raised": "#16161f",
    "lp-surface-overlay": "#050508",
    "lp-border": "#26262e",
    "lp-border-muted": "#1a1a22",
    "lp-cursor": "#1e2a4a",
    "lp-modal-bg": "#0a0a10",
    "lp-overlay": "black 65%",
    "lp-chip-bg": "#16161f",
}

TOKEN_NAMES: tuple[str, ...] = tuple(DARK_TOKENS)
