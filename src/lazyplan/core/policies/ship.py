"""Pure Markdown rendering for the outcome ship note."""

from __future__ import annotations

from typing import Any


def _cell(value: Any) -> str:
    """One line that cannot break a table or heading."""
    return " ".join(str(value).split()).replace("|", "\\|")


def _short(value: Any, limit: int = 80) -> str:
    """One-line excerpt."""
    text = _cell(value)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _head(payload: dict[str, Any]) -> list[str]:
    plan = payload.get("plan") or {}
    criteria = payload.get("criteria") or {}
    milestones = payload.get("milestones") or []
    tasks = payload.get("tasks") or {}
    done_milestones = sum(1 for item in milestones if item.get("status") == "done")
    done_tasks = int(tasks.get("done", 0) or 0)
    total_tasks = int(tasks.get("total", 0) or 0)
    covered = int(criteria.get("evidence", 0) or 0)
    total = int(criteria.get("total", 0) or 0)
    return [
        f"# P{plan.get('id')} — {_cell(plan.get('name', ''))}",
        "",
        f"**Status:** {plan.get('status', '-')} · "
        f"**Milestones:** {done_milestones}/{len(milestones)} · "
        f"**Tasks:** {done_tasks}/{total_tasks}",
        f"**Evidence:** {covered}/{total} criteria proven",
        "",
    ]


def _why(payload: dict[str, Any]) -> list[str]:
    why = str(payload.get("why", "") or "").strip()
    return ["## Why", "", why, ""] if why else []


def _shipped(payload: dict[str, Any]) -> list[str]:
    lines = ["## What shipped", ""]
    milestones = payload.get("milestones") or []
    if not milestones:
        lines.append("no milestones")
    for milestone in milestones:
        lines.append(
            f"- M{milestone['id']} {_cell(milestone.get('title', ''))} "
            f"({milestone.get('done', 0)}/{milestone.get('total', 0)})"
        )
    done_tasks = payload.get("done_tasks") or []
    for task in done_tasks:
        lines.append(f"- [x] T{task['id']} {_cell(task.get('title', ''))}")
    lines.append("")
    return lines


def _evidence(payload: dict[str, Any]) -> list[str]:
    audit = payload.get("audit") or {}
    criteria = payload.get("criteria") or {}
    return [
        "## Evidence",
        "",
        f"- Criteria proven: {int(criteria.get('evidence', 0) or 0)}"
        f"/{int(criteria.get('total', 0) or 0)}",
        f"- Commit coverage: {float(audit.get('coverage', 1.0)):.0%}",
        f"- Trace coverage: {float(audit.get('trace_coverage', 1.0)):.0%}",
        f"- Evidence rows: {int(audit.get('evidence_total', 0) or 0)}",
        "",
    ]


def _commits(payload: dict[str, Any]) -> list[str]:
    lines = ["## Commits", ""]
    commits = payload.get("commits") or []
    if not commits:
        lines.append("none linked")
    for commit in commits:
        link = f" ([link]({commit['url']}))" if commit.get("url") else ""
        lines.append(
            f"- `{str(commit.get('sha', ''))[:12]}` {_short(commit.get('subject', ''))}{link}"
        )
    return lines


def _pulls(payload: dict[str, Any]) -> list[str]:
    lines = ["## Pull requests", ""]
    pulls = payload.get("prs") or []
    if not pulls:
        lines.append("none linked")
    for pull in pulls:
        link = f" ([link]({pull['url']}))" if pull.get("url") else ""
        lines.append(
            f"- #{pull.get('number')} {_short(pull.get('title', ''))} "
            f"({pull.get('state', 'unknown')}){link}"
        )
    return lines


def _risks(payload: dict[str, Any], detail: bool = True) -> list[str]:
    lines = ["## Residual risks", ""]
    questions = payload.get("questions") or []
    blocked = payload.get("blocked") or []
    stale = int(payload.get("stale", 0) or 0)
    open_criteria = payload.get("open_criteria") or []
    lines.append(f"- Open questions: {len(questions)}")
    lines.append(f"- Blocked tasks: {len(blocked)}")
    lines.append(f"- Stale commits: {stale}")
    lines.append(f"- Open criteria: {len(open_criteria)}")
    if detail:
        for question in questions:
            lines.append(f"  - Q{question['id']}: {_cell(question.get('text', ''))}")
        for task in blocked:
            lines.append(f"  - T{task['id']} {_cell(task.get('title', ''))}")
        for criterion in open_criteria[:10]:
            lines.append(f"  - {_cell(criterion.get('text', ''))}")
    lines.append("")
    return lines


def _followups(payload: dict[str, Any], notes: bool = True) -> list[str]:
    lines = ["## Follow-ups", ""]
    open_tasks = payload.get("open_tasks") or []
    if not open_tasks:
        lines.append("none")
    for task in open_tasks:
        lines.append(f"- [ ] T{task['id']} {_cell(task.get('title', ''))}")
    if notes:
        for note in payload.get("notes") or []:
            lines.append(f"- @{note.get('actor', '')}: {_short(note.get('text', ''), 120)}")
    lines.append("")
    return lines


def _render(payload: dict[str, Any], drop: tuple[str, ...] = ()) -> str:
    lines = _head(payload) + _why(payload) + _shipped(payload) + _evidence(payload)
    if "commits" not in drop:
        lines.extend(_commits(payload))
        lines.append("")
    if "prs" not in drop:
        lines.extend(_pulls(payload))
        lines.append("")
    if "risks" not in drop:
        lines.extend(_risks(payload, detail="risk_detail" not in drop))
    if "notes" not in drop:
        lines.extend(_followups(payload, notes=True))
    else:
        lines.extend(_followups(payload, notes=False))
    return "\n".join(lines).rstrip() + "\n"


def render(payload: dict[str, Any], max_chars: int = 0) -> str:
    """Render one deterministic ship note; trim optional sections when capped."""
    for drop in (
        (),
        ("commits",),
        ("commits", "prs"),
        ("commits", "prs", "notes"),
        ("commits", "prs", "notes", "risk_detail"),
    ):
        text = _render(payload, drop)
        if not max_chars or len(text) <= max_chars:
            return text
    notice = f"\n\n[truncated to {max_chars} chars]\n"
    return text[: max(0, max_chars - len(notice))].rstrip() + notice
