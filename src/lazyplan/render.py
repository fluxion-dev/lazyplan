"""Terminal rendering helpers (labels, tree, show, markdown).

Single source of truth for row grammar lives in design.py; this module
only composes multi-line views for the CLI.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .design import INDENT, project_label, story_label, task_label

if TYPE_CHECKING:
    from .models import Status
    from .store import Store


def tree_lines(
    store: Store,
    status: Status | None,
    project_id: int | None,
    owner: str | None = None,
    priority: str | None = None,
) -> list[str]:
    """Indented tree lines using the canonical design labels."""
    lines = []
    for p, stories in store.tree(
        status=status, project_id=project_id, owner=owner, priority=priority
    ):
        lines.append(f"{INDENT[0]}{project_label(p)}")
        for s, tasks in stories:
            lines.append(f"{INDENT[1]}{story_label(s, store)}")
            for t in tasks:
                lines.append(f"{INDENT[2]}{task_label(t, store)}")
    return lines


def render_full(kind: str, full: dict) -> str:
    """Human-readable `lpui show`: narrative + links + children."""
    lines: list[str] = []

    def links_block(items: list[dict]) -> None:
        """Append link lines."""
        for li in items:
            label = f" ({li['label']})" if li.get("label") else ""
            lines.append(f"  @{li['id']}: {li['url']}{label}")

    def crit_block(items: list[dict]) -> None:
        """Append checklist lines."""
        for c in items:
            box = "x" if c.get("done") else " "
            lines.append(f"  [{box}] #{c['id']} {c['text']}")

    def meta_line(obj: dict, key: str, prefix: str) -> None:
        """Append a 'label: value' line when the value is set."""
        if obj.get(key):
            lines.append(f"{prefix}: {obj[key]}")

    if kind == "project":
        p = full["project"]
        lines.append(
            f"P#{p['id']} [{p['status']}] {p['name']} ({p['start_date']}..{p['end_date']})"
        )
        for label, key in (
            ("goal", "goal"),
            ("success", "success_metrics"),
            ("in-scope", "scope_in"),
            ("out-of-scope", "scope_out"),
            ("assumes", "assumptions"),
        ):
            meta_line(p, key, label)
        if p.get("description"):
            lines.append(f"\n{p['description']}")
        if full.get("milestones"):
            lines.append("\nmilestones:")
            for m in full["milestones"]:
                lines.append(f"  ◆ {m['date'] or '????-??-??'} M#{m['id']} {m['title']}")
        if full.get("risks"):
            lines.append("\nrisks:")
            for r in full["risks"]:
                lines.append(
                    f"  ⚠ R#{r['id']} {r['title']} ({r['likelihood']}x{r['impact']}"
                    f" · {r['status']})"
                )
                if r.get("mitigation"):
                    lines.append(f"    mitigates: {r['mitigation']}")
        if full.get("critical"):
            lines.append("\ncritical: " + " -> ".join(f"S#{i}" for i in full["critical"]))
        for entry in full["stories"]:
            s = entry["story"]
            own = f" @{s['owner']}" if s.get("owner") else ""
            lines.append(
                f"\n  S#{s['id']} [{s['status']}] {s['title']}{own}"
                f" ({s['start_date']}..{s['end_date']})"
            )
    elif kind == "story":
        s = full["story"]
        own = f" @{s['owner']}" if s.get("owner") else ""
        lines.append(
            f"S#{s['id']} [{s['status']}] {s['title']}{own}"
            f" (P#{s['project_id']} · {s['start_date']}..{s['end_date']})"
        )
        for label, key in (
            ("priority", "priority"),
            ("labels", "labels"),
            ("estimate", "estimate"),
            ("blocked by", "blocked_by"),
        ):
            if s.get(key):
                lines.append(f"{label}: {s[key]}")
        if s.get("description"):
            lines.append(f"\n{s['description']}")
        if full["links"]:
            lines.append("\nlinks:")
            links_block(full["links"])
        if full.get("criteria"):
            lines.append("\ncriteria:")
            crit_block(full["criteria"])
        for entry in full["tasks"]:
            t = entry["task"]
            town = f" @{t['owner']}" if t.get("owner") else ""
            lines.append(f"\n  T#{t['id']} [{t['status']}] {t['title']}{town}")
            if t.get("description"):
                lines.append(f"  {t['description']}")
    else:
        t = full["task"]
        own = f" @{t['owner']}" if t.get("owner") else ""
        lines.append(
            f"T#{t['id']} [{t['status']}] {t['title']}{own}"
            f" (S#{t['story_id']} · ~{t.get('estimate', '')}"
            f" · {t['start_date']}..{t['end_date']})"
        )
        for label, key in (
            ("priority", "priority"),
            ("labels", "labels"),
            ("blocked by", "blocked_by"),
        ):
            if t.get(key):
                lines.append(f"{label}: {t[key]}")
        if t.get("description"):
            lines.append(f"\n{t['description']}")
        if full["links"]:
            lines.append("\nlinks:")
            links_block(full["links"])
        if full.get("criteria"):
            lines.append("\ncriteria:")
            crit_block(full["criteria"])
    return "\n".join(lines)


def render_markdown(data: dict) -> str:
    """Human/portable markdown export of the whole db."""
    lines = ["# lazyplan export", ""]
    for entry in data.get("projects", []):
        p = entry["project"]
        lines.append(
            f"## P#{p['id']} {p['name']} [{p['status']}] ({p['start_date']}..{p['end_date']})"
        )
        if p.get("goal"):
            lines.append(f"> goal: {p['goal']}")
        for ms in entry.get("milestones", []):
            lines.append(f"- ◆ {ms['date']} {ms['title']}")
        for risk in entry.get("risks", []):
            lines.append(
                f"- ⚠ {risk['title']} ({risk['likelihood']}x{risk['impact']} · {risk['status']})"
            )
        for sentry in entry.get("stories", []):
            s = sentry["story"]
            lines.append(f"\n### S#{s['id']} {s['title']} [{s['status']}]")
            for tentry in sentry.get("tasks", []):
                t = tentry["task"]
                box = "x" if t["status"] == "done" else " "
                lines.append(f"- [{box}] T#{t['id']} {t['title']}")
        lines.append("")
    return "\n".join(lines)
