"""Semantic colour tokens for the lazyplan dark and light themes."""

from __future__ import annotations

DARK_TOKENS: dict[str, str] = {
    "lp-surface": "#161b22",
    "lp-surface-alt": "#0d1117",
    "lp-surface-raised": "#21262d",
    "lp-border": "#30363d",
    "lp-border-muted": "#21262d",
    "lp-text-muted": "#8b949e",
    "lp-text-faint": "#6e7681",
    "lp-accent": "#3fb950",
    "lp-accent-muted": "#238636",
    "lp-focus": "#58a6ff",
    "lp-status-todo": "#8b949e",
    "lp-status-doing": "#d29922",
    "lp-status-done": "#3fb950",
    "lp-status-blocked": "#f85149",
    "lp-chip-bg": "#21262d",
    "lp-chip-fg": "#c9d1d9",
    "lp-chart-bar": "#3fb950",
    "lp-chart-axis": "#8b949e",
    "lp-chart-label": "#c9d1d9",
    "lp-diff-add": "#3fb950",
    "lp-diff-remove": "#f85149",
}

LIGHT_TOKENS: dict[str, str] = {
    "lp-surface": "#f6f8fa",
    "lp-surface-alt": "#ffffff",
    "lp-surface-raised": "#ffffff",
    "lp-border": "#d0d7de",
    "lp-border-muted": "#e6eaef",
    "lp-text-muted": "#57606a",
    "lp-text-faint": "#6e7781",
    "lp-accent": "#1a7f37",
    "lp-accent-muted": "#2da44e",
    "lp-focus": "#0969da",
    "lp-status-todo": "#6e7781",
    "lp-status-doing": "#9a6700",
    "lp-status-done": "#1a7f37",
    "lp-status-blocked": "#cf222e",
    "lp-chip-bg": "#eef1f4",
    "lp-chip-fg": "#1f2328",
    "lp-chart-bar": "#1a7f37",
    "lp-chart-axis": "#57606a",
    "lp-chart-label": "#1f2328",
    "lp-diff-add": "#1a7f37",
    "lp-diff-remove": "#cf222e",
}

TOKEN_NAMES: tuple[str, ...] = tuple(DARK_TOKENS)
