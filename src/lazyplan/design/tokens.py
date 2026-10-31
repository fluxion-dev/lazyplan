"""Visual tokens shared by the CLI and the TUI.

Keep colours, heights, borders, indentation, and icon maps here. Row text
lives in ``text``, labels and rows in ``rows``, and empty/message wording in
``empty``. The package ``__init__`` re-exports the public names.
"""

from __future__ import annotations

# -- visual tokens -------------------------------------------------------
BORDER = "solid green"
PANEL_HEIGHT = "1fr"
BAR_HEIGHT = "1"  # activity line + statusbar: exactly one row each

APP_CSS = f"""
#panel {{ height: {PANEL_HEIGHT}; border: {BORDER}; }}
#main {{ height: {PANEL_HEIGHT}; }}
#nav {{ width: 1fr; min-width: 30; border-right: {BORDER}; }}
#preview {{ width: 1fr; min-width: 30; padding: 0 1; }}
#main.narrow #preview {{ display: none; }}
#main.narrow #nav {{ border-right: none; }}
#metrics {{ height: 13; padding: 0 1; }}
#metrics.narrow {{ display: none; }}
.metric-card {{ width: 1fr; height: 1fr; min-width: 18; padding: 0 1; margin: 0 1 0 0; border: {BORDER}; }}
.metric-title {{ height: 1; color: $text-muted; text-style: bold; }}
.metric-empty {{ height: 1fr; }}
.metric-head {{ height: 2; }}
#metrics PlotextPlot {{ height: 1fr; }}
#preview-body {{ height: auto; }}
#status {{ height: {BAR_HEIGHT}; background: $primary; }}
#hints {{ height: {BAR_HEIGHT}; background: $panel; color: $text-muted; padding: 0 1; }}
#dlg {{ width: 90%; max-width: 72; height: auto; border: {BORDER}; padding: 1; }}
#dlg TextArea {{ height: 4; }}
#f-why, #f-what {{ height: 3; }}
#dlg #palette-scroll {{ height: auto; max-height: 16; }}
#help {{ width: 90%; height: 90%; border: {BORDER}; padding: 1; }}
#help-scroll {{ height: 1fr; }}
#detail-page {{ height: 1fr; border: {BORDER}; padding: 0 1; }}
#detail-head {{ height: 1; background: $panel; padding: 0 1; }}
#detail-read {{ height: 1fr; padding: 0 1; }}
#detail-edit {{ height: 1fr; padding: 0 1; }}
#detail-edit TextArea {{ height: 5; }}
#detail-hints {{ height: 1; background: $panel; color: $text-muted; padding: 0 1; }}
#source-page {{ height: 1fr; border: {BORDER}; padding: 0 1; }}
#source-head {{ height: 3; background: $panel; padding: 0 1; }}
#source-filter {{ height: 3; }}
#source-main {{ height: 1fr; }}
#source-tree-wrap {{ width: 1fr; min-width: 30; border-right: {BORDER}; }}
#source-preview {{ width: 1fr; min-width: 30; padding: 0 1; }}
#source-preview-body {{ height: auto; }}
ModalScreen {{ align: center middle; }}
#dlg Button, #help Button, #detail-page Button {{ min-width: 0; width: auto; height: 3; padding: 0 1; }}
.btn-row {{ width: 1fr; height: auto; }}
"""

# -- label language ---------------------------------------------------------
# Canonical row grammar (plain text: `lpui list`, tests):
#   GLYPH KIND<id> title  (GLYPH is ○ todo, ◐ doing, ● done;
#   KIND is P (plan), M (milestone), T (task))
# Single-cell glyphs keep rows aligned in every terminal; the TUI adds
# color, the CLI adds ANSI on a tty, and plain output stays script-safe.
# Tree indentation is the viewer's job ("", "  ", "    " for CLI).

INDENT = ("", "  ", "    ")

# -- setup wizard palette ---------------------------------------------------
# ANSI codes stay here so setup output matches the TUI without a second
# styling language. Callers opt in through color_enabled().
ANSI = {
    "reset": "\x1b[0m",
    "bold": "\x1b[1m",
    "dim": "\x1b[2m",
    "cyan": "\x1b[36m",
    "green": "\x1b[32m",
    "yellow": "\x1b[33m",
    "red": "\x1b[31m",
    "white": "\x1b[97m",
}

ICONS = {
    "setup": "◆",
    "check": "✓",
    "circle": "○",
    "arrow": "→",
    "warn": "⚠",
    "dot": "·",
}
ASCII_ICONS = {
    "setup": "*",
    "check": "[x]",
    "circle": "[ ]",
    "arrow": "->",
    "warn": "!",
    "dot": "-",
}
