"""lazyplan design system — stable façade over focused design modules.

Rows, glyphs, chips, empty states, and messages live here. Command names,
key hints, and help live in ``help`` and ``palette`` (re-exported below) so
the palette, keymap, help screen, and ``lpui help`` cannot drift.

Maps to the four UXPin consistency types:
  visual    - tokens in ``tokens`` (border, heights, icons, CSS)
  functional- same keys everywhere; TUI is keyboard-only, agents use `lpui`
              the same thing in every view
  internal  - CLI and TUI render labels, empty states, and help from THESE
              helpers, never from drum-rolled local format strings
  external  - shell conventions: `--help`, `--json`, `prog --db PATH verb`,
              `KEY=value` env overrides, non-zero exit on error

Rule: if you add a view, command, or message, add it here or in
``palette`` first. Importers keep using ``lazyplan.design``.
"""

from __future__ import annotations

from ..help import HELP_TEXT as HELP_TEXT
from ..help import KEYMAP as KEYMAP
from ..kinds import LABEL_LETTERS as LABEL_LETTERS
from ..kinds import MILESTONE as MILESTONE
from ..kinds import PLAN as PLAN
from ..kinds import TASK as TASK
from ..palette import PALETTE_COMMANDS as PALETTE_COMMANDS
from ..palette import PALETTE_SECTIONS as PALETTE_SECTIONS
from .empty import EMPTY_COMMITS as EMPTY_COMMITS
from .empty import EMPTY_FEED as EMPTY_FEED
from .empty import EMPTY_NO_PLANS as EMPTY_NO_PLANS
from .empty import msg_error as msg_error
from .empty import msg_no_head as msg_no_head
from .empty import msg_no_vcs as msg_no_vcs
from .empty import msg_not_found as msg_not_found
from .row_stats import RowStats as RowStats
from .row_stats import render_stats as render_stats
from .row_stats import stats_layout as stats_layout
from .rows import apply_mark as apply_mark
from .rows import milestone_label as milestone_label
from .rows import milestone_row as milestone_row
from .rows import plan_label as plan_label
from .rows import plan_row as plan_row
from .rows import task_label as task_label
from .rows import task_row as task_row
from .text import SPINNER_FRAMES as SPINNER_FRAMES
from .text import SPINNER_INTERVAL as SPINNER_INTERVAL
from .text import STATUS_ANSI as STATUS_ANSI
from .text import STATUS_GLYPH as STATUS_GLYPH
from .text import STATUS_RICH as STATUS_RICH
from .text import escape_markup as escape_markup
from .text import pr_chip as pr_chip
from .text import progress_bar as progress_bar
from .text import progress_text as progress_text
from .text import repo_project_name as repo_project_name
from .text import spinner_glyph as spinner_glyph
from .text import status_prefix as status_prefix
from .text import status_word as status_word
from .text import truncate as truncate
from .tokens import ANSI as ANSI
from .tokens import ASCII_ICONS as ASCII_ICONS
from .tokens import ICONS as ICONS
from .tokens import INDENT as INDENT

__all__ = [
    "ANSI",
    "ASCII_ICONS",
    "EMPTY_COMMITS",
    "EMPTY_FEED",
    "EMPTY_NO_PLANS",
    "HELP_TEXT",
    "ICONS",
    "INDENT",
    "KEYMAP",
    "LABEL_LETTERS",
    "MILESTONE",
    "PALETTE_COMMANDS",
    "PALETTE_SECTIONS",
    "PLAN",
    "RowStats",
    "SPINNER_FRAMES",
    "SPINNER_INTERVAL",
    "STATUS_ANSI",
    "STATUS_GLYPH",
    "STATUS_RICH",
    "TASK",
    "apply_mark",
    "escape_markup",
    "milestone_label",
    "milestone_row",
    "msg_error",
    "msg_no_head",
    "msg_no_vcs",
    "msg_not_found",
    "plan_label",
    "plan_row",
    "pr_chip",
    "progress_bar",
    "progress_text",
    "repo_project_name",
    "render_stats",
    "spinner_glyph",
    "stats_layout",
    "status_prefix",
    "status_word",
    "task_label",
    "task_row",
    "truncate",
]
