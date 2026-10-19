"""Terminal rendering helpers (labels, tree, show, markdown).

Single source of truth for row grammar lives in design.py; this module
only composes multi-line views for the CLI.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .design import INDENT, project_label, status_word, story_label, task_label

if TYPE_CHECKING:
    from .models import Status
    from .store import Store


def tree_lines(
    store: Store,
    status: Status | None,
    project_id: int | None,
    priority: str | None = None,
    dot: str = "plain",
    archived: str = "hide",
) -> list[str]:
    """Indented tree lines using the canonical design labels."""
    lines = []
    for p, stories in store.tree(
        status=status, project_id=project_id, priority=priority, archived=archived
    ):
        lines.append(f"{INDENT[0]}{project_label(p, store, dot)}")
        for s, tasks in stories:
            lines.append(f"{INDENT[1]}{story_label(s, store, dot)}")
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


def render_full(kind: str, full: dict) -> str:
    """Human-readable `lpui show`: why/what + criteria + commits + children."""
    lines: list[str] = []

    def crit_block(items: list[dict]) -> None:
        """Append checklist lines."""
        for c in items:
            box = "x" if c.get("done") else " "
            lines.append(f"  [{box}] #{c['id']} {c['text']}")

    def commits_block(items: list[dict]) -> None:
        """Append linked-commit lines."""
        for line in render_commits(items).splitlines():
            lines.append(f"  {line}")

    def meta_line(label: str, value: object) -> None:
        """Append a 'label: value' line when the value is set."""
        if value:
            lines.append(f"{label}: {value}")

    if kind == "project":
        p = full["project"]
        pri = f" !{p['priority']}" if p.get("priority") else ""
        lines.append(f"{status_word(p['status'])} P#{p['id']} {p['name']}{pri}")
        meta_line("why", p.get("goal"))
        if p.get("description"):
            lines.append(f"\nwhat: {p['description']}")
        if full.get("criteria"):
            lines.append("\nacceptance:")
            crit_block(full["criteria"])
        if full.get("links"):
            lines.append("\ncommits:")
            commits_block(full["links"])
        for entry in full["stories"]:
            s = entry["story"]
            spri = f" !{s['priority']}" if s.get("priority") else ""
            lines.append(f"\n  {status_word(s['status'])} S#{s['id']} {s['title']}{spri}")
    elif kind == "story":
        s = full["story"]
        spri = f" !{s['priority']}" if s.get("priority") else ""
        lines.append(
            f"{status_word(s['status'])} S#{s['id']} {s['title']}{spri} (P#{s['project_id']})"
        )
        if s.get("description"):
            lines.append(f"\ndetails: {s['description']}")
        if full.get("criteria"):
            lines.append("\nacceptance:")
            crit_block(full["criteria"])
        if full.get("links"):
            lines.append("\ncommits:")
            commits_block(full["links"])
        for entry in full["tasks"]:
            t = entry["task"]
            tpri = f" !{t['priority']}" if t.get("priority") else ""
            lines.append(f"\n  {status_word(t['status'])} T#{t['id']} {t['title']}{tpri}")
            if t.get("description"):
                lines.append(f"  {t['description']}")
    else:
        t = full["task"]
        tpri = f" !{t['priority']}" if t.get("priority") else ""
        lines.append(
            f"{status_word(t['status'])} T#{t['id']} {t['title']}{tpri} (S#{t['story_id']})"
        )
        if t.get("description"):
            lines.append(f"\ndetails: {t['description']}")
        if full.get("criteria"):
            lines.append("\nacceptance:")
            crit_block(full["criteria"])
        if full.get("links"):
            lines.append("\ncommits:")
            commits_block(full["links"])
    return "\n".join(lines)


def render_markdown(data: dict) -> str:
    """Human/portable markdown export of the whole db."""
    lines = ["# lazyplan export", ""]
    for entry in data.get("projects", []):
        p = entry["project"]
        pri = f" !{p['priority']}" if p.get("priority") else ""
        lines.append(f"## {status_word(p['status'])} P#{p['id']} {p['name']} {pri}".rstrip())
        if p.get("goal"):
            lines.append(f"> why: {p['goal']}")
        if p.get("description"):
            lines.append(f"> what: {p['description']}")
        for c in entry.get("criteria", []):
            box = "x" if c.get("done") else " "
            lines.append(f"- [{box}] {c['text']}")
        for sentry in entry.get("stories", []):
            s = sentry["story"]
            lines.append(f"\n### {status_word(s['status'])} S#{s['id']} {s['title']}")
            for tentry in sentry.get("tasks", []):
                t = tentry["task"]
                box = "x" if t["status"] == "done" else " "
                lines.append(f"- [{box}] T#{t['id']} {t['title']}")
        lines.append("")
    return "\n".join(lines)
