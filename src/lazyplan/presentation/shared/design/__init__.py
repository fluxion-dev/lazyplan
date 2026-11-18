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
``palette`` first. Importers keep using ``lazyplan.presentation.shared.design``.
"""

from __future__ import annotations

from ....core.kinds import LABEL_LETTERS as LABEL_LETTERS
from ....core.kinds import MILESTONE as MILESTONE
from ....core.kinds import PLAN as PLAN
from ....core.kinds import TASK as TASK
from ..help import HELP_TEXT as HELP_TEXT
from ..help import KEYMAP as KEYMAP
from ..palette import PALETTE_COMMANDS as PALETTE_COMMANDS
from ..palette import PALETTE_SECTIONS as PALETTE_SECTIONS
from .actions import action_bar as action_bar
from .empty import EMPTY_APPROVAL as EMPTY_APPROVAL
from .empty import EMPTY_COMMITS as EMPTY_COMMITS
from .empty import EMPTY_FEED as EMPTY_FEED
from .empty import EMPTY_NEEDS as EMPTY_NEEDS
from .empty import EMPTY_NO_PLANS as EMPTY_NO_PLANS
from .empty import EMPTY_NO_PLANS_HINT as EMPTY_NO_PLANS_HINT
from .empty import EMPTY_NO_PLANS_TITLE as EMPTY_NO_PLANS_TITLE
from .empty import EMPTY_PLAN_QUEUE_HINT as EMPTY_PLAN_QUEUE_HINT
from .empty import EMPTY_PLAN_QUEUE_TITLE as EMPTY_PLAN_QUEUE_TITLE
from .empty import PANEL_PLAN_QUEUE_TITLE as PANEL_PLAN_QUEUE_TITLE
from .empty import PANEL_PLAN_REVIEW_TITLE as PANEL_PLAN_REVIEW_TITLE
from .empty import empty_state as empty_state
from .empty import msg_error as msg_error
from .empty import msg_no_head as msg_no_head
from .empty import msg_no_vcs as msg_no_vcs
from .empty import msg_not_found as msg_not_found
from .facts import branch_word as branch_word
from .facts import checkout_state as checkout_state
from .facts import evidence_label as evidence_label
from .facts import short_sha as short_sha
from .facts import stale_word as stale_word
from .icons import DEFAULT_ICONS as DEFAULT_ICONS
from .icons import ENV_VAR as ICON_ENV
from .icons import ICON_NAMES as ICON_NAMES
from .icons import ICON_PALETTES as ICON_PALETTES
from .icons import active_icons as active_icons
from .icons import apply_icons as apply_icons
from .icons import choose_icons as choose_icons
from .icons import icon_palette as icon_palette
from .icons import next_icons as next_icons
from .icons import remember_icons as remember_icons
from .icons import remembered_icons as remembered_icons
from .icons import resolve_icons as resolve_icons
from .icons import select_icons as select_icons
from .row_stats import RowStats as RowStats
from .row_stats import render_stats as render_stats
from .row_stats import stats_layout as stats_layout
from .rows import milestone_label as milestone_label
from .rows import milestone_row as milestone_row
from .rows import plan_label as plan_label
from .rows import plan_row as plan_row
from .rows import task_label as task_label
from .rows import task_row as task_row
from .text import STATUS_ANSI as STATUS_ANSI
from .text import STATUS_GLYPH as STATUS_GLYPH
from .text import STATUS_RICH as STATUS_RICH
from .text import escape_markdown as escape_markdown
from .text import escape_markup as escape_markup
from .text import pr_chip as pr_chip
from .text import progress_text as progress_text
from .text import repo_project_name as repo_project_name
from .text import status_word as status_word
from .text import truncate as truncate
from .tokens import ANSI as ANSI
from .tokens import ASCII_ICONS as ASCII_ICONS
from .tokens import ICONS as ICONS
from .tokens import INDENT as INDENT
from .tokens import KIND_ICON as KIND_ICON
from .tokens import SECTION_ICON as SECTION_ICON
from .tokens import STATE_ICON as STATE_ICON

__all__ = [
    "branch_word",
    "checkout_state",
    "evidence_label",
    "short_sha",
    "stale_word",
    "ANSI",
    "action_bar",
    "active_icons",
    "apply_icons",
    "ASCII_ICONS",
    "EMPTY_COMMITS",
    "EMPTY_FEED",
    "EMPTY_APPROVAL",
    "EMPTY_NEEDS",
    "EMPTY_NO_PLANS",
    "EMPTY_NO_PLANS_HINT",
    "EMPTY_NO_PLANS_TITLE",
    "EMPTY_PLAN_QUEUE_HINT",
    "EMPTY_PLAN_QUEUE_TITLE",
    "choose_icons",
    "DEFAULT_ICONS",
    "empty_state",
    "HELP_TEXT",
    "ICON_ENV",
    "ICON_NAMES",
    "ICON_PALETTES",
    "ICONS",
    "icon_palette",
    "INDENT",
    "KEYMAP",
    "KIND_ICON",
    "LABEL_LETTERS",
    "MILESTONE",
    "PALETTE_COMMANDS",
    "PALETTE_SECTIONS",
    "PANEL_PLAN_QUEUE_TITLE",
    "PANEL_PLAN_REVIEW_TITLE",
    "PLAN",
    "RowStats",
    "SECTION_ICON",
    "STATUS_ANSI",
    "STATUS_GLYPH",
    "STATUS_RICH",
    "STATE_ICON",
    "TASK",
    "escape_markdown",
    "escape_markup",
    "milestone_label",
    "milestone_row",
    "msg_error",
    "msg_no_head",
    "msg_no_vcs",
    "msg_not_found",
    "next_icons",
    "plan_label",
    "plan_row",
    "pr_chip",
    "progress_text",
    "remember_icons",
    "remembered_icons",
    "render_stats",
    "repo_project_name",
    "resolve_icons",
    "select_icons",
    "stats_layout",
    "status_word",
    "task_label",
    "task_row",
    "truncate",
]
