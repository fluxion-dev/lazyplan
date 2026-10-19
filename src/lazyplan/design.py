"""lazyplan design system — single source of truth for consistency.

Maps to the four UXPin consistency types:
  visual    - tokens below (border, heights, placeholder/command prefixes)
  functional- same keys everywhere; TUI is keyboard-only, agents use `lpui`
              the same thing in every view
  internal  - CLI and TUI render labels, empty states, and help from THESE
              helpers, never from drum-rolled local format strings
  external  - shell conventions: `--help`, `--json`, `prog --db PATH verb`,
              `KEY=value` env overrides, non-zero exit on error

Rule: if you add a view, command, or message, add it here first.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .models import Status

if TYPE_CHECKING:
    from .models import Project, Task, UserStory
    from .store import Store

# -- visual tokens -------------------------------------------------------
BORDER = "solid green"
PANEL_HEIGHT = "1fr"
BAR_HEIGHT = "1"  # activity line + statusbar: exactly one row each

APP_CSS = f"""
#panel {{ height: {PANEL_HEIGHT}; border: {BORDER}; }}
#activity {{ height: {BAR_HEIGHT}; background: $surface; }}
#statusbar {{ height: {BAR_HEIGHT}; background: $primary; }}
#dlg {{ width: 60; height: auto; border: {BORDER}; padding: 1; }}
ModalScreen {{ align: center middle; }}
"""

# -- label language ---------------------------------------------------------
# Canonical row grammar (plain text: `lpui list`, tests):
#   KIND#id [status] !p0 title [1/2✓]
# TUI project rows are Rich markup (Tree labels parse it):
#   [reverse] P1 [/] !p0 title
# Tree indentation is the viewer's job ("", "  ", "    " for CLI).

INDENT = ("", "  ", "    ")


def _status(value: Status | str) -> str:
    return value.value if isinstance(value, Status) else str(value)


def priority_tag(priority: str) -> str:
    """!p0-style priority marker, or empty."""
    return f" !{priority}" if priority else ""


def crit_tag(done: int | None, total: int | None) -> str:
    """[done/total check] progress suffix, or empty."""
    if not total:
        return ""
    return f" [{done or 0}/{total}✓]"


def pill_tag(text: str) -> str:
    """Reverse-video pill for TUI rows (Rich markup; Tree parses it)."""
    return f"[reverse] {text} [/]"


def _escape_markup(text: str) -> str:
    """Escape `[` so titles render literally in markup-parsed TUI rows."""
    return text.replace("[", "\\[")


def _crit_progress(store: Store | None, kind: str, obj_id: int) -> tuple[int | None, int | None]:
    if store is None:
        return None, None
    return store.criteria_progress(kind, obj_id)


def project_label(p: Project, store: Store | None = None) -> str:
    """Canonical row label for a project (plain text: CLI, tests)."""
    done, total = _crit_progress(store, "project", p.id)
    return (
        f"P#{p.id} [{_status(p.status)}]{priority_tag(p.priority)} {p.name}{crit_tag(done, total)}"
    )


def project_row(p: Project, store: Store | None = None) -> str:
    """TUI project row (Rich markup): pill number + priority + title."""
    return f"{pill_tag(f'P{p.id}')}{priority_tag(p.priority)} {_escape_markup(p.name)}"


def story_label(s: UserStory, store: Store | None = None) -> str:
    """Canonical row label for a story."""
    done, total = _crit_progress(store, "story", s.id)
    return (
        f"S#{s.id} [{_status(s.status)}]{priority_tag(s.priority)} {s.title}{crit_tag(done, total)}"
    )


def task_label(t: Task, store: Store | None = None) -> str:
    """Canonical row label for a task."""
    done, total = _crit_progress(store, "task", t.id)
    return (
        f"T#{t.id} [{_status(t.status)}]{priority_tag(t.priority)} {t.title}{crit_tag(done, total)}"
    )


# -- empty states (identical wording everywhere) --------------------------
EMPTY_NO_PROJECTS = "No projects yet — press n to seed, or run: lpui seed"
EMPTY_FILTERED = "(filter hides everything — f/o to clear, or n to add)"
EMPTY_FEED = "(no activity yet — agents write via `lpui add-task ...`)"


# -- messages ---------------------------------------------------------------
def msg_not_found(kind: str, obj_id: int) -> str:
    """Standard '<kind> #<id> not found' message."""
    return f"{kind} #{obj_id} not found"


def msg_error(exc: BaseException) -> str:
    """Standard 'error: <exc>' message."""
    return f"error: {exc}"


# -- `lpui init` skill-wizard text (wizard prints these; keep wording stable) --
INIT_SKILLS_TITLE = "== lpui init: agent skills =="
INIT_SKILLS_EXPLAIN = "One universal skill teaches your agents to use `lpui` for planning."
INIT_SKILLS_COVERAGE = (
    "Install target `.agents/skills/lazyplan/SKILL.md` auto-loads in "
    "OpenCode, Codex, Gemini CLI, and Cursor. A `.claude/skills/` copy is "
    "added automatically when Claude Code is detected."
)
INIT_SKILLS_DONE = "Done. Restart your agent session, then try `lpui list`."
INIT_SKILLS_COMMIT_TIP = (
    "Tip: commit `.agents/skills/lazyplan/`, `.claude/skills/` (if any), and AGENTS.md."
)


# -- help (TUI `?` overlay AND `lpui help` render this same text) -------------
HELP_TEXT = """lazyplan — local project journal (TUI is keyboard-only; agents use lpui)
tree: j/k or up/down + click · left/right collapse/expand · enter detail
n new (context) · P/S/T new project/story/task · e edit · d delete
space cycle status · c tick criteria · z/Z fold one/all
f status filter · o project filter
r refresh · ? help · q quit
workflow: interview why/what/acceptance criteria, add-project, cut prioritized stories + tasks"""
