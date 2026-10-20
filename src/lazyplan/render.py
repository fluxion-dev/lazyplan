"""Terminal rendering helpers (labels, tree, show, markdown).

Single source of truth for row grammar lives in design.py; this module
only composes multi-line views for the CLI.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .design import INDENT, milestone_label, plan_label, status_word, task_label
from .services import tree as service_tree

if TYPE_CHECKING:
    from .models import Status
    from .store import Store


def tree_lines(
    store: Store,
    status: Status | None,
    plan_id: int | None,
    priority: str | None = None,
    dot: str = "plain",
    archived: str = "hide",
    limit: int | None = None,
    repo: str | None = None,
) -> list[str]:
    """Indented tree lines using the canonical design labels."""
    lines = []
    for p, milestones in service_tree(
        store,
        status=status,
        plan_id=plan_id,
        priority=priority,
        archived=archived,
        limit=limit,
        repo=repo,
    ):
        lines.append(f"{INDENT[0]}{plan_label(p, store, dot)}")
        for s, tasks in milestones:
            lines.append(f"{INDENT[1]}{milestone_label(s, store, dot)}")
            for t in tasks:
                lines.append(f"{INDENT[2]}{task_label(t, store, dot)}")
    return lines


def render_commits(links: list[dict]) -> str:
    """Human-readable commit list for `lpui commits` and `show` sections."""
    lines = []
    for link in links:
        sha = str(link.get("sha", ""))
        short = sha[:12] if len(sha) >= 12 else sha
        subject = str(link.get("subject", "") or "").strip()
        author = str(link.get("author", "") or "").strip()
        extra = f" ({author})" if author and subject else author
        line = f"{short} {subject}{extra}".rstrip() if (subject or extra) else short
        lines.append(line)
    return "\n".join(lines)


def _append_crit(lines: list[str], items: list[dict]) -> None:
    """Append checklist lines."""
    for c in items:
        box = "x" if c.get("done") else " "
        lines.append(f"  [{box}] #{c['id']} {c['text']}")


def _append_commits(lines: list[str], items: list[dict]) -> None:
    """Append linked-commit lines."""
    for line in render_commits(items).splitlines():
        lines.append(f"  {line}")


def _append_repos(lines: list[str], full: dict) -> None:
    """Append linked-repo lines (effective wins over explicit)."""
    items = full.get("effective_repos") or full.get("repos") or []
    if items:
        lines.append("\nrepos:")
        for r in items:
            path = str(r.get("repo_path", "") or "")
            remote = str(r.get("repo_remote", "") or "")
            lines.append(f"  {path}" + (f" ({remote})" if remote else ""))


def _append_common(lines: list[str], full: dict) -> None:
    """Shared show sections: acceptance + commits + repos."""
    if full.get("criteria"):
        lines.append("\nacceptance:")
        _append_crit(lines, full["criteria"])
    if full.get("links"):
        lines.append("\ncommits:")
        _append_commits(lines, full["links"])
    _append_repos(lines, full)


def _render_plan_full(full: dict, lines: list[str]) -> None:
    """Plan show body."""
    from .design import status_word

    p = full["plan"]
    lines.append(f"{status_word(p['status'])} P#{p['id']} {p['name']}")
    if p.get("goal"):
        lines.append(f"why: {p['goal']}")
    if p.get("description"):
        lines.append(f"\nwhat: {p['description']}")
    _append_common(lines, full)
    for entry in full["milestones"]:
        s = entry["milestone"]
        lines.append(f"\n  {status_word(s['status'])} M#{s['id']} {s['title']}")


def _render_milestone_full(full: dict, lines: list[str]) -> None:
    """Milestone show body."""
    from .design import status_word

    s = full["milestone"]
    lines.append(f"{status_word(s['status'])} M#{s['id']} {s['title']} (P#{s['plan_id']})")
    if s.get("description"):
        lines.append(f"\ndetails: {s['description']}")
    _append_common(lines, full)
    for entry in full["tasks"]:
        t = entry["task"]
        lines.append(f"\n  {status_word(t['status'])} T#{t['id']} {t['title']}")
        if t.get("description"):
            lines.append(f"  {t['description']}")


def _render_task_full(full: dict, lines: list[str]) -> None:
    """Task show body."""
    from .design import status_word

    t = full["task"]
    lines.append(f"{status_word(t['status'])} T#{t['id']} {t['title']} (M#{t['milestone_id']})")
    if t.get("description"):
        lines.append(f"\ndetails: {t['description']}")
    _append_common(lines, full)


def render_full(kind: str, full: dict) -> str:
    """Human-readable `lpui show`: why/what + criteria + commits + repos + children."""
    lines: list[str] = []
    if kind == "plan":
        _render_plan_full(full, lines)
    elif kind == "milestone":
        _render_milestone_full(full, lines)
    else:
        _render_task_full(full, lines)
    return "\n".join(lines)


def render_markdown(data: dict) -> str:
    """Human/portable markdown export of the whole db."""
    lines = ["# lazyplan export", ""]
    for entry in data.get("plans", []):
        p = entry["plan"]
        lines.append(f"## {status_word(p['status'])} P#{p['id']} {p['name']}".rstrip())
        if p.get("goal"):
            lines.append(f"> why: {p['goal']}")
        if p.get("description"):
            lines.append(f"> what: {p['description']}")
        for c in entry.get("criteria", []):
            box = "x" if c.get("done") else " "
            lines.append(f"- [{box}] {c['text']}")
        for sentry in entry.get("milestones", []):
            s = sentry["milestone"]
            lines.append(f"\n### {status_word(s['status'])} M#{s['id']} {s['title']}")
            for tentry in sentry.get("tasks", []):
                t = tentry["task"]
                box = "x" if t["status"] == "done" else " "
                lines.append(f"- [{box}] T#{t['id']} {t['title']}")
        lines.append("")
    return "\n".join(lines)
