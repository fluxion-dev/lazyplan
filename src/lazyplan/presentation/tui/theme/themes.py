"""Register and select the lazyplan Textual themes."""

from __future__ import annotations

import os

from textual.app import App
from textual.theme import Theme

from .tokens import DARK_TOKENS, LIGHT_TOKENS, VOID_TOKENS

DARK_NAME = "lazyplan-dark"
LIGHT_NAME = "lazyplan-light"
VOID_NAME = "lazyplan-void"
ENV_VAR = "LAZYPLAN_THEME"

LAZYPLAN_DARK = Theme(
    name=DARK_NAME,
    primary="#89b4fa",
    secondary="#cba6f7",
    accent="#b4befe",
    warning="#f9e2af",
    error="#f38ba8",
    success="#a6e3a1",
    foreground="#cdd6f4",
    background="#1e1e2e",
    surface="#313244",
    panel="#181825",
    boost="#11111b",
    dark=True,
    variables=dict(DARK_TOKENS),
)

LAZYPLAN_LIGHT = Theme(
    name=LIGHT_NAME,
    primary="#1e66f5",
    secondary="#8839ef",
    accent="#7287fd",
    warning="#df8e1d",
    error="#d20f39",
    success="#40a02b",
    foreground="#4c4f69",
    background="#eff1f5",
    surface="#ccd0da",
    panel="#e6e9ef",
    boost="#ffffff",
    dark=False,
    variables=dict(LIGHT_TOKENS),
)

LAZYPLAN_VOID = Theme(
    name=VOID_NAME,
    primary="#89b4fa",
    secondary="#cba6f7",
    accent="#b4befe",
    warning="#f9e2af",
    error="#f38ba8",
    success="#a6e3a1",
    foreground="#cdd6f4",
    background="#000000",
    surface="#16161f",
    panel="#070709",
    boost="#0a0a10",
    dark=True,
    variables=dict(VOID_TOKENS),
)

#: Registration and cycling order: mocha, OLED void, latte.
THEMES: tuple[Theme, ...] = (LAZYPLAN_DARK, LAZYPLAN_VOID, LAZYPLAN_LIGHT)
THEME_NAMES: tuple[str, ...] = tuple(theme.name for theme in THEMES)

_ALIASES = {
    "dark": DARK_NAME,
    "mocha": DARK_NAME,
    "lazyplan-dark": DARK_NAME,
    "lazyplan_dark": DARK_NAME,
    "void": VOID_NAME,
    "oled": VOID_NAME,
    "black": VOID_NAME,
    "lazyplan-void": VOID_NAME,
    "lazyplan_void": VOID_NAME,
    "light": LIGHT_NAME,
    "latte": LIGHT_NAME,
    "lazyplan-light": LIGHT_NAME,
    "lazyplan_light": LIGHT_NAME,
}


def choose_theme(value: str | None = None) -> str:
    """Resolve a theme name from an explicit value or ``LAZYPLAN_THEME``."""
    raw = (value if value is not None else os.environ.get(ENV_VAR, "")).strip().lower()
    return _ALIASES.get(raw, DARK_NAME)


def next_theme(current: str) -> str:
    """Return the next theme in register/cycle order."""
    try:
        index = THEME_NAMES.index(current)
    except ValueError:
        return THEME_NAMES[0]
    return THEME_NAMES[(index + 1) % len(THEME_NAMES)]


def register_themes(app: App) -> str:
    """Register every theme and activate the selected one."""
    for theme in THEMES:
        app.register_theme(theme)
    selected = choose_theme()
    app.theme = selected
    return selected
