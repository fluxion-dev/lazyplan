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

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING

from .kinds import LABEL_LETTERS, MILESTONE, PLAN, TASK
from .models import Status

if TYPE_CHECKING:
    from .models import Milestone, Plan, Task
    from .store import Store

# -- visual tokens -------------------------------------------------------
BORDER = "solid green"
PANEL_HEIGHT = "1fr"
BAR_HEIGHT = "1"  # activity line + statusbar: exactly one row each

APP_CSS = f"""
#panel {{ height: {PANEL_HEIGHT}; border: {BORDER}; }}
#main {{ height: {PANEL_HEIGHT}; }}
#nav {{ width: 1fr; min-width: 30; border-right: {BORDER}; }}
#preview {{ width: 1fr; min-width: 30; padding: 0 1; }}
#preview-body {{ height: auto; }}
#status {{ height: {BAR_HEIGHT}; background: $primary; }}
#dlg {{ width: 60; height: auto; border: {BORDER}; padding: 1; }}
ModalScreen {{ align: center middle; }}
#dlg Button {{ min-width: 0; width: auto; height: 1; padding: 0 1; }}
.btn-row {{ width: 1fr; height: auto; }}
"""

# -- label language ---------------------------------------------------------
# Canonical row grammar (plain text: `lpui list`, tests):
#   GLYPH KIND#id title   (GLYPH is ⬜ todo, 🔵 doing, ✅ done;
#   KIND is P (plan), M (milestone), T (task))
# Priority stays on the model as a hidden attribute (future TODO
# reprioritization) and never renders in headers.
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


def pill_tag(text: str) -> str:
    """Reverse-video pill for TUI rows (Rich markup; Tree parses it)."""
    return f"[reverse] {text} [/]"


def commits_chip(shas: Sequence[str] | None) -> str:
    """Short-SHA chips, one per linked commit; empty when there are no links."""
    if not shas:
        return ""
    return " ".join(pill_tag(s[:12]) for s in shas)


def repo_project_name(repo: Mapping[str, object] | None) -> str:
    """Project name for a linked repo: remote repo name, else checkout basename."""
    if not repo:
        return ""
    remote = str(repo.get("repo_remote") or "").strip().rstrip("/")
    if remote:
        tail = remote.rsplit(":", 1)[-1].rsplit("/", 1)[-1]
        if tail.lower().endswith(".git"):
            tail = tail[: -len(".git")]
        if tail:
            return tail
    path = str(repo.get("repo_path") or "").strip().rstrip("/")
    if path:
        return path.rsplit("/", 1)[-1] or path
    return ""


def repos_chip(repos: Sequence[Mapping[str, object]] | None) -> str:
    """Pill chips, one per linked repo project; empty when there are no links."""
    names = [n for n in (repo_project_name(r) for r in repos or []) if n]
    if not names:
        return ""
    return " ".join(pill_tag(n) for n in names)


def _escape_markup(text: str) -> str:
    """Escape `[` so titles render literally in markup-parsed TUI rows."""
    return text.replace("[", "\\[")


_CORE_SPEC: dict[str, tuple[str, str]] = {
    PLAN: (LABEL_LETTERS[PLAN], "name"),
    MILESTONE: (LABEL_LETTERS[MILESTONE], "title"),
    TASK: (LABEL_LETTERS[TASK], "title"),
}


def _core(kind: str, obj: Plan | Milestone | Task, store: Store | None) -> str:
    """Label body without the leading status word, shared by label and row."""
    letter, title_attr = _CORE_SPEC[kind]
    title = getattr(obj, title_attr)
    return f"{letter}#{obj.id} {title}"


def _label(kind: str, obj: Plan | Milestone | Task, store: Store | None, dot: str) -> str:
    """Canonical row label: status word + body (plain text: CLI, tests)."""
    return f"{status_word(obj.status, dot)} {_core(kind, obj, store)}"


def _row(
    kind: str,
    obj: Plan | Milestone | Task,
    store: Store | None,
    links: Sequence[str] | None = None,
) -> str:
    """TUI row: Rich status word + escaped body + commit chips (when linked)."""
    base = f"{status_word(obj.status, 'rich')} {_escape_markup(_core(kind, obj, store))}"
    chips = commits_chip(links)
    return f"{base} {chips}" if chips else base


def plan_label(p: Plan, store: Store | None = None, dot: str = "plain") -> str:
    """Canonical row label for a plan (plain text: CLI, tests)."""
    base = _label("plan", p, store, dot)
    if store is None:
        return base
    names = [n for n in (repo_project_name(r) for r in store.effective_repos("plan", p.id)) if n]
    return f"{base} [{', '.join(names)}]" if names else base


def plan_row(
    p: Plan,
    store: Store | None = None,
    links: Sequence[str] | None = None,
    repos: Sequence[Mapping[str, object]] | None = None,
) -> str:
    """TUI plan row (Rich markup): status + pill + title + chips."""
    base = f"{status_word(p.status, 'rich')} {pill_tag(f'P{p.id}')} {_escape_markup(p.name)}"
    chips = commits_chip(links)
    repo_chips = repos_chip(repos)
    if repo_chips:
        chips = f"{chips} {repo_chips}" if chips else repo_chips
    return f"{base} {chips}" if chips else base


def milestone_label(s: Milestone, store: Store | None = None, dot: str = "plain") -> str:
    """Canonical row label for a milestone."""
    return _label("milestone", s, store, dot)


def milestone_row(
    s: Milestone, store: Store | None = None, links: Sequence[str] | None = None
) -> str:
    """TUI milestone row (Rich markup): status word + canonical label + chips."""
    return _row("milestone", s, store, links)


def task_label(t: Task, store: Store | None = None, dot: str = "plain") -> str:
    """Canonical row label for a task."""
    return _label("task", t, store, dot)


def task_row(t: Task, store: Store | None = None, links: Sequence[str] | None = None) -> str:
    """TUI task row (Rich markup): status word + canonical label + chips."""
    return _row("task", t, store, links)


# -- empty states (identical wording everywhere) --------------------------
EMPTY_NO_PLANS = "No plans yet — press n to seed, or run: lpui seed"
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


# -- palette commands (single source; modal palette lists these) --
PALETTE_COMMANDS: tuple[tuple[str, str], ...] = (
    ("create", "create…"),
    ("open-detail", "open detail"),
    ("export-md", "export plan .md"),
    ("criteria", "tick criteria"),
    ("delete", "delete with confirm"),
    ("toggle-status", "cycle status"),
    ("fold", "fold one"),
    ("fold-all", "fold all"),
    ("filter", "cycle status filter"),
    ("filter-text", "filter by text…"),
    ("show-all", "show all / capped"),
    ("refresh", "refresh"),
    ("help", "help"),
    ("quit", "quit"),
)

# -- palette sections (single source; modal renders headers + commands) --
PALETTE_SECTIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Create", ("create",)),
    ("Edit", ("open-detail", "delete")),
    ("Track", ("toggle-status", "criteria")),
    ("View", ("fold", "fold-all", "filter", "filter-text", "show-all", "refresh")),
    ("App", ("export-md", "help", "quit")),
)

# -- keymap (canonical table; HELP_TEXT below mirrors it) -------------------
# (key, action, surfaces)
KEYMAP: tuple[tuple[str, str, str], ...] = (
    ("j/k, up/down, click", "move cursor / select", "tree"),
    ("enter, double-click", "detail", "tree"),
    ("left/right", "fold / unfold", "tree"),
    ("c", "command palette", "tree"),
    ("escape", "clear filter / cancel", "tree, modals"),
    ("esc", "cancel", "modals"),
)


# -- help (TUI `?` overlay AND `lpui help` render this same text) -------------
HELP_TEXT = """lazyplan — local plan journal (TUI is keyboard-only; agents use lpui)
tree: j/k or up/down + click select · left/right fold/unfold · enter/double-click detail
c palette: type a command, enter runs it · filter by text narrows · escape clears
modals: esc cancels
workflow: interview why/what/acceptance criteria, add-plan, cut prioritized milestones + tasks"""
