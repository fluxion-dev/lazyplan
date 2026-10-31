"""lazyplan design system — single source of truth for consistency.

Rows, glyphs, chips, empty states, and messages live here. Command names,
key hints, and help live in `commands.py` (imported at the bottom of the
corresponding sections) so the palette, keymap, help screen, and `lpui
help` cannot drift.

Maps to the four UXPin consistency types:
  visual    - tokens below (border, heights, placeholder/command prefixes)
  functional- same keys everywhere; TUI is keyboard-only, agents use `lpui`
              the same thing in every view
  internal  - CLI and TUI render labels, empty states, and help from THESE
              helpers, never from drum-rolled local format strings
  external  - shell conventions: `--help`, `--json`, `prog --db PATH verb`,
              `KEY=value` env overrides, non-zero exit on error

Rule: if you add a view, command, or message, add it here or in
`commands.py` first.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING

from .help import HELP_TEXT as HELP_TEXT
from .help import KEYMAP as KEYMAP
from .kinds import LABEL_LETTERS, MILESTONE, PLAN, TASK
from .models import Status
from .palette import PALETTE_COMMANDS as PALETTE_COMMANDS
from .palette import PALETTE_SECTIONS as PALETTE_SECTIONS

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
#main.narrow #preview {{ display: none; }}
#main.narrow #nav {{ border-right: none; }}
#metrics {{ height: 12; padding: 0 1; }}
#metrics.narrow {{ display: none; }}
.metric-card {{ width: 1fr; height: 1fr; min-width: 18; padding: 0 1; margin: 0 1 0 0; border: {BORDER}; }}
.metric-title {{ height: 1; color: $text-muted; text-style: bold; }}
.metric-body {{ height: 1fr; }}
.metric-empty {{ height: 1fr; }}
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

STATUS_GLYPH = {"todo": "○", "doing": "◐", "done": "●"}
STATUS_ANSI = {"todo": "90", "doing": "33", "done": "32"}
STATUS_RICH = {"todo": "dim", "doing": "yellow", "done": "green"}
BLOCKED_RICH = "red"

METRIC_BAR_WIDTH = 10

HEATMAP_CELL = "█"
HEATMAP_EMPTY = "#30363d"
HEATMAP_SHADES = ("#0e4429", "#006d32", "#26a641", "#39d353")


def metric_bar(value: int, maximum: int, width: int = METRIC_BAR_WIDTH) -> str:
    """Rich-markup micro-bar scaled to *maximum*."""
    if maximum <= 0:
        return "[dim]" + "░" * width + "[/]"
    filled = min(width, max(0, round(value * width / maximum)))
    return f"[green]{'█' * filled}[/][dim]{'░' * (width - filled)}[/]"


def heatmap_color(count: int, peak: int) -> str:
    """Palette color for a daily count, scaled to the busiest day."""
    if peak <= 0 or count <= 0:
        return HEATMAP_EMPTY
    if count >= peak:
        return HEATMAP_SHADES[3]
    if count * 2 >= peak:
        return HEATMAP_SHADES[2]
    if count * 4 >= peak:
        return HEATMAP_SHADES[1]
    return HEATMAP_SHADES[0]


# The doing glyph is the first frame, so static output and frame 0 agree.
# All four frames are one terminal cell; the TUI advances them on a timer.
SPINNER_FRAMES = ("◐", "◓", "◑", "◒")
SPINNER_INTERVAL = 0.16


def _status(value: Status | str) -> str:
    return value.value if isinstance(value, Status) else str(value)


def spinner_glyph(frame: int) -> str:
    """One frame of the doing spinner; any integer wraps into the cycle."""
    return SPINNER_FRAMES[frame % len(SPINNER_FRAMES)]


def status_word(status: Status | str, dot: str = "plain") -> str:
    """Status glyph: plain, ANSI-colored (tty CLI), or Rich markup (TUI)."""
    name = _status(status)
    glyph = STATUS_GLYPH.get(name, "?")
    if dot == "ansi":
        return f"\x1b[{STATUS_ANSI.get(name, '37')}m{glyph}\x1b[0m"
    if dot == "rich":
        return f"[{STATUS_RICH.get(name, 'white')}]{glyph}[/]"
    if dot != "plain":
        raise ValueError("dot must be plain|ansi|rich")
    return glyph


def status_prefix(status: Status | str, frame: int = 0) -> str:
    """Rich row prefix: spinner frame for doing, static glyph otherwise."""
    if _status(status) == "doing" and frame:
        return f"[{STATUS_RICH['doing']}]{spinner_glyph(frame)}[/]"
    return status_word(status, "rich")


def truncate(text: str, width: int | None) -> str:
    """Trim to `width` cells with an ellipsis; None or wide enough is a no-op."""
    if width is None or len(text) <= width:
        return text
    if width <= 0:
        return ""
    if width == 1:
        return "…"
    return text[: width - 1].rstrip() + "…"


def progress_text(done: int, total: int) -> str:
    """Compact progress used on plan and milestone rows."""
    return f"{done}/{total}"


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
    """Dim chips, one per linked repo project; empty when there are no links."""
    names = [n for n in (repo_project_name(r) for r in repos or []) if n]
    if not names:
        return ""
    return " ".join(f"[dim]{n}[/]" for n in names)


def commits_chip(
    shas: Sequence[str] | None,
    limit: int = 2,
    stale: bool = False,
) -> str:
    """Dim short-SHA chips, capped, with an optional stale marker."""
    if not shas:
        return ""
    shown = list(shas[: max(1, limit)])
    text = " ".join(f"[dim]{s[:12]}[/]" for s in shown)
    if len(shas) > len(shown):
        text += f" [dim]+{len(shas) - len(shown)}[/]"
    if stale:
        text += " [red]![/]"
    return text


def source_chip(commit_count: int = 0, pull_count: int = 0, stale: int = 0) -> str:
    """Compact provenance counts for plan and milestone rows."""
    parts: list[str] = []
    if commit_count:
        parts.append(f"{commit_count}c")
    if pull_count:
        parts.append(f"{pull_count} PR")
    if stale:
        parts.append(f"{stale} stale")
    return f"[dim]{' · '.join(parts)}[/]" if parts else ""


_PR_STYLE = {
    "merged": ("green", "PR"),
    "open": ("yellow", "PR"),
    "draft": ("dim", "PR"),
    "closed": ("red", "PR"),
    "": ("dim", "PR"),
}


def pr_chip(state: str = "", checks: str = "") -> str:
    """Compact cached-PR chip; empty when the task has no cached PR."""
    if not state and not checks:
        return ""
    color, label = _PR_STYLE.get(state, ("dim", "PR"))
    if checks == "fail":
        color, label = "red", "PR!"
    elif checks == "pending":
        color, label = "yellow", "PR…"
    return f"[{color}]{label}[/]"


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
    return f"{letter}{obj.id} {title}"


def _label(kind: str, obj: Plan | Milestone | Task, store: Store | None, dot: str) -> str:
    """Canonical row label: status word + body (plain text: CLI, tests)."""
    return f"{status_word(obj.status, dot)} {_core(kind, obj, store)}"


def _row(
    kind: str,
    obj: Plan | Milestone | Task,
    links: Sequence[str] | None = None,
    progress: tuple[int, int] | None = None,
    width: int | None = None,
    pr_state: str = "",
    pr_checks: str = "",
    stale: bool = False,
    source_counts: tuple[int, int, int] | None = None,
    claim_actor: str = "",
    claim_expired: bool = False,
    blocked: bool = False,
    marked: bool = False,
) -> str:
    """TUI row: Rich status glyph + dim id + bold title + progress/chips."""
    letter, title_attr = _CORE_SPEC[kind]
    id_part = f"{letter}{obj.id}"
    title = getattr(obj, title_attr)
    if source_counts is not None:
        chips = source_chip(*source_counts)
    else:
        chips = commits_chip(links, stale=stale)
    suffix = ""
    plain_suffix = ""
    if progress is not None:
        done, total = progress
        suffix += f" [dim]{progress_text(done, total)}[/]"
        plain_suffix += f" {progress_text(done, total)}"
    if marked:
        suffix += " [bold green]✓[/]"
        plain_suffix += " ✓"
    if blocked:
        suffix += " [red]blocked[/]"
        plain_suffix += " blocked"
    if claim_actor:
        marker = "!" if claim_expired else ""
        suffix += f" [dim]@{_escape_markup(claim_actor)}{marker}[/]"
        plain_suffix += f" @{claim_actor}{marker}"
    if chips:
        suffix += f" {chips}"
        if source_counts is not None:
            commits, pulls, stale_count = source_counts
            plain_suffix += f" {commits}c {pulls}PR {stale_count}stale"
        else:
            plain_suffix += " " + " ".join(sha[:12] for sha in (links or [])[:2])
    pr = pr_chip(pr_state, pr_checks)
    if pr:
        suffix += f" {pr}"
        plain_suffix += " PR"
    prefix_plain = f"{status_word(obj.status)} {id_part} "
    available = None if width is None else width - len(prefix_plain) - len(plain_suffix)
    title = truncate(title, available)
    style = "dim" if obj.status == Status.DONE else "bold"
    return (
        f"{status_prefix(obj.status)} [dim]{id_part}[/] [{style}]{_escape_markup(title)}[/]{suffix}"
    )


def plan_label(p: Plan, store: Store | None = None, dot: str = "plain") -> str:
    """Canonical row label for a plan (plain text: CLI, tests)."""
    base = _label("plan", p, store, dot)
    if store is None:
        return base
    names = [n for n in (repo_project_name(r) for r in store.effective_repos("plan", p.id)) if n]
    return f"{base} [{', '.join(names)}]" if names else base


def _plan_source_suffix(
    links: Sequence[str] | None,
    repos: Sequence[Mapping[str, object]] | None,
    source_counts: tuple[int, int, int] | None,
) -> tuple[str, str]:
    """Rich and plain source suffix (counts and repo chips) for a plan row."""
    chips = source_chip(*source_counts) if source_counts is not None else commits_chip(links)
    all_chips = " ".join(chip for chip in (chips, repos_chip(repos)) if chip)
    rich = f" {all_chips}" if all_chips else ""
    plain = ""
    if all_chips:
        if source_counts is not None:
            commits, pulls, stale_count = source_counts
            plain += f" {commits}c {pulls}PR {stale_count}stale"
        else:
            plain += " " + " ".join(sha[:12] for sha in (links or [])[:2])
        plain += " " + " ".join(
            part for part in (repo_project_name(r) for r in (repos or [])) if part
        )
    return rich, plain


def plan_row(
    p: Plan,
    store: Store | None = None,
    links: Sequence[str] | None = None,
    repos: Sequence[Mapping[str, object]] | None = None,
    progress: tuple[int, int] | None = None,
    width: int | None = None,
    source_counts: tuple[int, int, int] | None = None,
    marked: bool = False,
) -> str:
    """TUI plan row (Rich markup): glyph + id + title + progress + chips."""
    id_part = f"P{p.id}"
    suffix, plain_suffix = _plan_source_suffix(links, repos, source_counts)
    if progress is not None:
        done, total = progress
        suffix = f" [dim]{progress_text(done, total)}[/]" + suffix
        plain_suffix = f" {progress_text(done, total)}" + plain_suffix
    if marked:
        suffix += " [bold green]✓[/]"
        plain_suffix += " ✓"
    prefix_plain = f"{status_word(p.status)} {id_part} "
    available = None if width is None else width - len(prefix_plain) - len(plain_suffix)
    title = truncate(p.name, available)
    style = "dim" if p.status == Status.DONE else "bold"
    return (
        f"{status_prefix(p.status)} [dim]{id_part}[/] [{style}]{_escape_markup(title)}[/]{suffix}"
    )


def milestone_label(s: Milestone, store: Store | None = None, dot: str = "plain") -> str:
    """Canonical row label for a milestone."""
    return _label("milestone", s, store, dot)


def milestone_row(
    s: Milestone,
    store: Store | None = None,
    links: Sequence[str] | None = None,
    progress: tuple[int, int] | None = None,
    width: int | None = None,
    source_counts: tuple[int, int, int] | None = None,
    marked: bool = False,
) -> str:
    """TUI milestone row (Rich markup): glyph + id + title + progress + chips."""
    return _row(
        "milestone",
        s,
        links,
        progress,
        width,
        source_counts=source_counts,
        marked=marked,
    )


def task_label(t: Task, store: Store | None = None, dot: str = "plain") -> str:
    """Canonical row label for a task, including blocked state and claim holder."""
    base = _label("task", t, store, dot)
    if t.blocked:
        base += " [blocked]"
    if store is None:
        return base
    claim = store.get_claim(t.id)
    return f"{base} @{claim.actor}" if claim is not None else base


def task_row(
    t: Task,
    store: Store | None = None,
    links: Sequence[str] | None = None,
    width: int | None = None,
    pr_state: str = "",
    pr_checks: str = "",
    stale: bool = False,
    claim_actor: str = "",
    claim_expired: bool = False,
    blocked: bool = False,
    marked: bool = False,
) -> str:
    """TUI task row (Rich markup): glyph + id + title + claim/PR/commit chips."""
    return _row(
        "task",
        t,
        links,
        None,
        width,
        pr_state,
        pr_checks,
        stale,
        claim_actor=claim_actor,
        claim_expired=claim_expired,
        blocked=blocked,
        marked=marked,
    )


# -- empty states (identical wording everywhere) --------------------------
EMPTY_NO_PLANS = "No plans yet — press n to create one, or run: lpui plan add"
EMPTY_FEED = "No activity yet — agents write with `lpui task add`."


# -- messages ---------------------------------------------------------------
def msg_not_found(kind: str, obj_id: int) -> str:
    """Standard '<kind> #<id> not found' message."""
    return f"{kind} {obj_id} not found"


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


def escape_markup(text: str) -> str:
    """Escape `[` for Rich markup surfaces (preview, rows)."""
    return _escape_markup(text)
