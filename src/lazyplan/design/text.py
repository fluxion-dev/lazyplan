"""Glyphs, status words, truncation, and compact provenance chips."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from ..models import Status

STATUS_GLYPH = {"todo": "○", "doing": "◐", "done": "●"}
STATUS_ANSI = {"todo": "90", "doing": "33", "done": "32"}
STATUS_RICH = {"todo": "dim", "doing": "yellow", "done": "green"}

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


def progress_bar(done: int, total: int, width: int = 5) -> str:
    """A one-cell-per-column bar: ``▰▰▰▱▱`` for ``3/5``."""
    if total <= 0 or width <= 0:
        return ""
    filled = round(width * min(max(done, 0), total) / total)
    if done > 0 and filled == 0:
        filled = 1
    return "▰" * filled + "▱" * (width - filled)


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


def pr_label(state: str = "", checks: str = "") -> str:
    """Plain PR chip label; empty when the task has no cached PR."""
    if not state and not checks:
        return ""
    if checks == "fail":
        return "PR!"
    if checks == "pending":
        return "PR…"
    return "PR"


def pr_chip(state: str = "", checks: str = "") -> str:
    """Compact cached-PR chip; empty when the task has no cached PR."""
    label = pr_label(state, checks)
    if not label:
        return ""
    color, _ = _PR_STYLE.get(state, ("dim", "PR"))
    if checks == "fail":
        color = "red"
    elif checks == "pending":
        color = "yellow"
    return f"[{color}]{label}[/]"


def _escape_markup(text: str) -> str:
    """Escape `[` so titles render literally in markup-parsed TUI rows."""
    return text.replace("[", "\\[")


def escape_markup(text: str) -> str:
    """Escape `[` for Rich markup surfaces (preview, rows)."""
    return _escape_markup(text)
