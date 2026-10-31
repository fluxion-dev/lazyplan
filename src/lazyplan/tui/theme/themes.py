"""Register and select the lazyplan Textual themes."""

from __future__ import annotations

import os

from textual.app import App
from textual.theme import Theme

from .tokens import DARK_TOKENS, LIGHT_TOKENS

DARK_NAME = "lazyplan-dark"
LIGHT_NAME = "lazyplan-light"
ENV_VAR = "LAZYPLAN_THEME"

LAZYPLAN_DARK = Theme(
    name=DARK_NAME,
    primary="#238636",
    secondary="#1f6feb",
    accent="#3fb950",
    warning="#d29922",
    error="#f85149",
    success="#3fb950",
    foreground="#e6edf3",
    background="#0d1117",
    surface="#161b22",
    panel="#1c2128",
    boost="#21262d",
    dark=True,
    variables=dict(DARK_TOKENS),
)

LAZYPLAN_LIGHT = Theme(
    name=LIGHT_NAME,
    primary="#1a7f37",
    secondary="#0969da",
    accent="#2da44e",
    warning="#9a6700",
    error="#cf222e",
    success="#1a7f37",
    foreground="#1f2328",
    background="#ffffff",
    surface="#f6f8fa",
    panel="#eef1f4",
    boost="#ffffff",
    dark=False,
    variables=dict(LIGHT_TOKENS),
)

THEMES: tuple[Theme, ...] = (LAZYPLAN_DARK, LAZYPLAN_LIGHT)


def choose_theme(value: str | None = None) -> str:
    """Resolve a theme name from an explicit value or ``LAZYPLAN_THEME``."""
    raw = (value if value is not None else os.environ.get(ENV_VAR, "")).strip().lower()
    if raw in {"light", LIGHT_NAME, "lazyplan_light"}:
        return LIGHT_NAME
    return DARK_NAME


def register_themes(app: App) -> str:
    """Register both themes and activate the selected one."""
    for theme in THEMES:
        app.register_theme(theme)
    selected = choose_theme()
    app.theme = selected
    return selected
