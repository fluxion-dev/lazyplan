"""Plotext colour adapters for the two lazyplan themes."""

from __future__ import annotations

from typing import Any

from textual.app import App

LANE_TOKENS = (
    "lp-chart-lane-1",
    "lp-chart-lane-2",
    "lp-chart-lane-3",
    "lp-chart-lane-4",
    "lp-chart-lane-5",
    "lp-chart-lane-6",
)


def chart_color(app: App, token: str = "lp-chart-bar") -> str:
    """Map a semantic chart token to a Plotext colour name."""
    dark = app.current_theme.dark
    if token == "lp-chart-axis":
        return "gray"
    if token == "lp-chart-label":
        return "white" if dark else "black"
    if token == "lp-chart-bar":
        return "green+" if dark else "green"
    return "green"


def lane_color(app: App, index: int) -> str:
    """Hex colour for one timeline lane, cycling through the theme palette."""
    token = LANE_TOKENS[index % len(LANE_TOKENS)]
    return str(app.theme_variables.get(token) or app.theme_variables["lp-chart-bar"])


def token_rgb(app: App, token: str) -> tuple[int, int, int]:
    """RGB tuple for Plotext from one theme colour token."""
    value = str(app.theme_variables.get(token) or app.theme_variables["lp-surface"]).lstrip("#")
    return (
        int(value[0:2], 16),
        int(value[2:4], 16),
        int(value[4:6], 16),
    )


def lane_rgb(app: App, index: int) -> tuple[int, int, int]:
    """RGB tuple for Plotext from one timeline lane's theme colour."""
    return token_rgb(app, LANE_TOKENS[index % len(LANE_TOKENS)])


BASELINE_MIX = 0.65


def _blend(
    first: tuple[int, int, int], second: tuple[int, int, int], mix: float
) -> tuple[int, int, int]:
    """Blend two RGB colours, moving *mix* of the way to *second*."""
    return (
        round(first[0] + (second[0] - first[0]) * mix),
        round(first[1] + (second[1] - first[1]) * mix),
        round(first[2] + (second[2] - first[2]) * mix),
    )


def lane_baseline_rgb(app: App, index: int) -> tuple[int, int, int]:
    """Dim RGB tuple for a selected lane's full-span baseline."""
    return _blend(lane_rgb(app, index), token_rgb(app, "lp-surface"), BASELINE_MIX)


def apply_chart_theme(plot: Any, app: App) -> None:
    """Apply the chart canvas, axes, and tick colours for the active theme."""
    plot.canvas_color("default")
    plot.axes_color(chart_color(app, "lp-chart-axis"))
    plot.ticks_color(chart_color(app, "lp-chart-axis"))
