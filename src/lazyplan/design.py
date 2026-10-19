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
#   GLYPH KIND#id !p0 title [1/2✓]   (GLYPH is ⬜ todo, 🔵 doing, ✅ done)
# The glyph carries ANSI color on a tty CLI and Rich color in the TUI tree.
# Tree indentation is the viewer's job ("", "  ", "    " for CLI).

INDENT = ("", "  ", "    ")

STATUS_ANSI = {"todo": "33", "doing": "34", "done": "32"}
STATUS_RICH = {"todo": "yellow", "doing": "blue", "done": "green"}
STATUS_EMOJI = {"todo": "⬜", "doing": "🔵", "done": "✅"}


def _status(value: Status | str) -> str:
    return value.value if isinstance(value, Status) else str(value)


def status_word(status: Status | str, dot: str = "plain") -> str:
    """Status glyph: plain, ANSI-colored (tty CLI), or Rich markup (TUI)."""
    name = _status(status)
    glyph = STATUS_EMOJI.get(name, "?")
    if dot == "ansi":
        return f"\x1b[{STATUS_ANSI.get(name, '37')}m{glyph}\x1b[0m"
    if dot == "rich":
        return f"[{STATUS_RICH.get(name, 'white')}]{glyph}[/]"
    if dot != "plain":
        raise ValueError("dot must be plain|ansi|rich")
    return glyph


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


_CORE_SPEC: dict[str, tuple[str, str]] = {
    "project": ("P", "name"),
    "story": ("S", "title"),
    "task": ("T", "title"),
}


def _core(kind: str, obj: Project | UserStory | Task, store: Store | None) -> str:
    """Label body without the leading status word, shared by label and row."""
    letter, title_attr = _CORE_SPEC[kind]
    done, total = _crit_progress(store, kind, obj.id)
    title = getattr(obj, title_attr)
    return f"{letter}#{obj.id}{priority_tag(obj.priority)} {title}{crit_tag(done, total)}"


def _label(kind: str, obj: Project | UserStory | Task, store: Store | None, dot: str) -> str:
    """Canonical row label: status word + body (plain text: CLI, tests)."""
    return f"{status_word(obj.status, dot)} {_core(kind, obj, store)}"


def _row(kind: str, obj: Project | UserStory | Task, store: Store | None) -> str:
    """TUI row: Rich status word + escaped body."""
    return f"{status_word(obj.status, 'rich')} {_escape_markup(_core(kind, obj, store))}"


def project_label(p: Project, store: Store | None = None, dot: str = "plain") -> str:
    """Canonical row label for a project (plain text: CLI, tests)."""
    return _label("project", p, store, dot)


def project_row(p: Project, store: Store | None = None) -> str:
    """TUI project row (Rich markup): status word + pill number + priority + title."""
    return (
        f"{status_word(p.status, 'rich')} {pill_tag(f'P{p.id}')}"
        f"{priority_tag(p.priority)} {_escape_markup(p.name)}"
    )


def story_label(s: UserStory, store: Store | None = None, dot: str = "plain") -> str:
    """Canonical row label for a story."""
    return _label("story", s, store, dot)


def story_row(s: UserStory, store: Store | None = None) -> str:
    """TUI story row (Rich markup): status word + canonical label."""
    return _row("story", s, store)


def task_label(t: Task, store: Store | None = None, dot: str = "plain") -> str:
    """Canonical row label for a task."""
    return _label("task", t, store, dot)


def task_row(t: Task, store: Store | None = None) -> str:
    """TUI task row (Rich markup): status word + canonical label."""
    return _row("task", t, store)


# -- empty states (identical wording everywhere) --------------------------
EMPTY_NO_PROJECTS = "No projects yet — press n to seed, or run: lpui seed"
EMPTY_FEED = "(no activity yet — agents write via `lpui add-task ...`)"


# -- messages ---------------------------------------------------------------
def msg_not_found(kind: str, obj_id: int) -> str:
    """Standard '<kind> #<id> not found' message."""
    return f"{kind} #{obj_id} not found"


def msg_no_vcs() -> str:
    """Standard VCS-unavailable message (linking disabled outside a git repo)."""
    return "error: no VCS backend available (not in a git repo)"


def msg_no_head() -> str:
    """Standard no-commit message (git repo with no HEAD yet)."""
    return "error: no HEAD commit found (empty git repo?)"


EMPTY_COMMITS = "(no commits linked)"


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
tree: j/k or up/down + click select · left/right collapse/expand · enter/double-click detail
n new (context) · P/S/T new project/story/task · e edit · d delete
space cycle status · c tick criteria · z/Z fold one/all
f status filter · o project filter
r refresh · ? help · q quit
workflow: interview why/what/acceptance criteria, add-project, cut prioritized stories + tasks"""
