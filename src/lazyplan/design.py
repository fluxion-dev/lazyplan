"""lazyplan design system — single source of truth for consistency.

Maps to the four UXPin consistency types:
  visual    - tokens below (border, heights, placeholder/command prefixes)
  functional- same verbs everywhere (`lp` CLI == TUI command bar); same key does
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
CMD_HEIGHT = "3"  # command bar: input + frame, nano-style

APP_CSS = f"""
#panel {{ height: {PANEL_HEIGHT}; border: {BORDER}; }}
#activity {{ height: {BAR_HEIGHT}; background: $surface; }}
#statusbar {{ height: {BAR_HEIGHT}; background: $primary; }}
#cmdbar {{ height: {CMD_HEIGHT}; }}
#dlg {{ width: 60; height: auto; border: {BORDER}; padding: 1; }}
"""

# -- label language (used by `lp list` AND the TUI tree) ------------------
# Canonical row grammar:
#   KIND#id [status] !p0 title @owner (start..end) ~estimate [1/2✓] [!blocked by 3]
# Tree indentation is the viewer's job ("", "  ", "    " for CLI).

INDENT = ("", "  ", "    ")


def _status(value: Status | str) -> str:
    return value.value if isinstance(value, Status) else str(value)


def owner_tag(owner: str) -> str:
    """@owner suffix, or empty."""
    return f" @{owner}" if owner else ""


def priority_tag(priority: str) -> str:
    """!p0-style priority marker, or empty."""
    return f" !{priority}" if priority else ""


def crit_tag(done: int | None, total: int | None) -> str:
    """[done/total check] progress suffix, or empty."""
    if not total:
        return ""
    return f" [{done or 0}/{total}✓]"


def blocked_tag(blockers: list[int] | tuple, actively_blocked: bool) -> str:
    """[!]blocked-by marker, or empty."""
    if not blockers:
        return ""
    ids = ",".join(str(i) for i in blockers)
    mark = "!" if actively_blocked else ""
    return f" [{mark}blocked by {ids}]"


def date_span(start: str, end: str) -> str:
    """(start..end) range."""
    return f"({start}..{end})"


def project_label(p: Project) -> str:
    """Canonical row label for a project."""
    return f"P#{p.id} [{_status(p.status)}] {p.name} {date_span(p.start_date, p.end_date)}"


def _crit_progress(store: Store | None, kind: str, obj_id: int) -> tuple[int | None, int | None]:
    if store is None:
        return None, None
    return store.criteria_progress(kind, obj_id)


def story_label(s: UserStory, store: Store | None = None) -> str:
    """Canonical row label for a story."""
    done, total = _crit_progress(store, "story", s.id)
    blocked = store.is_blocked("story", s.id) if store is not None else False
    return (
        f"S#{s.id} [{_status(s.status)}]{priority_tag(s.priority)} {s.title}"
        f"{owner_tag(s.owner)} {date_span(s.start_date, s.end_date)}"
        f"{crit_tag(done, total)}{blocked_tag(s.blocked_by, blocked)}"
    )


def task_label(t: Task, store: Store | None = None) -> str:
    """Canonical row label for a task."""
    extra = "".join(
        [
            f" ~{t.estimate}" if t.estimate else "",
            f" {t.start_date}..{t.end_date}" if t.start_date or t.end_date else "",
        ]
    )
    done, total = _crit_progress(store, "task", t.id)
    blocked = store.is_blocked("task", t.id) if store is not None else False
    return (
        f"T#{t.id} [{_status(t.status)}]{priority_tag(t.priority)} {t.title}"
        f"{owner_tag(t.owner)}{extra}"
        f"{crit_tag(done, total)}{blocked_tag(t.blocked_by, blocked)}"
    )


# -- empty states (identical wording everywhere) --------------------------
EMPTY_NO_PROJECTS = "No projects yet — press n to seed, or run: lp seed"
EMPTY_FILTERED = "(filter hides everything — f/o/O to clear, or n to add)"
EMPTY_FEED = "(no activity yet — agents write via `lp add-task ...`)"


# -- messages ---------------------------------------------------------------
def msg_not_found(kind: str, obj_id: int) -> str:
    """Standard '<kind> #<id> not found' message."""
    return f"{kind} #{obj_id} not found"


def msg_error(exc: BaseException) -> str:
    """Standard 'error: <exc>' message."""
    return f"error: {exc}"


# -- `lp init` skill-wizard text (wizard prints these; keep wording stable) --
INIT_SKILLS_TITLE = "== lp init: agent skills =="
INIT_SKILLS_EXPLAIN = "One universal skill teaches your agents to use `lp` for planning."
INIT_SKILLS_COVERAGE = (
    "Install target `.agents/skills/lazyplan/SKILL.md` auto-loads in "
    "OpenCode, Codex, Gemini CLI, and Cursor. A `.claude/skills/` copy is "
    "added automatically when Claude Code is detected."
)
INIT_SKILLS_DONE = "Done. Restart your agent session, then try `lp list`."
INIT_SKILLS_COMMIT_TIP = (
    "Tip: commit `.agents/skills/lazyplan/`, `.claude/skills/` (if any), and AGENTS.md."
)


# -- help (TUI `?` overlay AND `lp help` render this same text) -------------
HELP_TEXT = """lazyplan — stream-of-consciousness console (lp CLI == : command bar)
views: 1 tree · 2 gantt · 3 feed · 4 proposals
move: j/k or up/down + click · left/right collapse/expand · enter edits detail in place
n new (context) · P/S/T new project/story/task · e edit · d delete
space cycle status · c tick criteria · z/Z fold one/all · +/- gantt zoom
f status filter · o project filter · O owner filter
s search · ctrl+p palette · a/x approve/reject proposal
r refresh · / command bar · ? help · q quit
: commands = lp verbs, e.g. show --kind story --id 1
agents: lp propose ... / lp ask ... (human approves/answers in UI)"""
