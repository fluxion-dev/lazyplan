"""Plotext colour adapters for the two lazyplan themes."""

from __future__ import annotations

from typing import Any

from textual.app import App


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


def apply_chart_theme(plot: Any, app: App) -> None:
    """Apply the chart canvas, axes, and tick colours for the active theme."""
    plot.canvas_color("default")
    plot.axes_color(chart_color(app, "lp-chart-axis"))
    plot.ticks_color(chart_color(app, "lp-chart-axis"))
