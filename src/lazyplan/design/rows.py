"""Canonical labels and TUI row markup for plans, milestones, and tasks."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING

from ..kinds import LABEL_LETTERS, MILESTONE, PLAN, TASK
from ..models import Status
from .text import (
    _escape_markup,
    commits_chip,
    pr_chip,
    progress_text,
    repo_project_name,
    repos_chip,
    source_chip,
    status_prefix,
    status_word,
    truncate,
)

if TYPE_CHECKING:
    from ..models import Milestone, Plan, Task
    from ..store import Store

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
