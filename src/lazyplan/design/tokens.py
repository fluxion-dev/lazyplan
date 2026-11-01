"""Shared non-colour design tokens.

Colours and layout live in the Textual theme and ``tui/css``. This module
keeps the plain-text indentation, ANSI codes, and icon maps that the CLI
and setup wizard reuse. Row text lives in ``text``, labels and rows in
``rows``, and empty/message wording in ``empty``. The package ``__init__``
re-exports the public names.
"""

from __future__ import annotations

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

# -- TUI icon language ------------------------------------------------------
# One cell each, so rows, preview headings, and the git pane stay aligned in
# any terminal. Kind icons label a breadcrumb; section icons head a preview
# block; state icons mark a checkout. The CLI keeps the plain label grammar.
KIND_ICON = {"plan": "◈", "milestone": "◇", "task": "▹"}
SECTION_ICON = {
    "why": "◎",
    "what": "◇",
    "details": "◇",
    "next": "▸",
    "acceptance": "✓",
    "notes": "✎",
    "comments": "✎",
    "source": "⌁",
    "git": "⎇",
    "repos": "⌂",
    "commits": "◆",
    "pulls": "⇄",
    "milestones": "◇",
    "tasks": "▹",
}
STATE_ICON = {"clean": "○", "dirty": "●", "detached": "⊘"}

ASCII_ICONS = {
    "setup": "*",
    "check": "[x]",
    "circle": "[ ]",
    "arrow": "->",
    "warn": "!",
    "dot": "-",
}
