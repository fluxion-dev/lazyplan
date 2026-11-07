"""Pure Markdown rendering for the review packet."""

from __future__ import annotations

import time
from typing import Any


def _cell(value: Any) -> str:
    """One table cell: no pipes or newlines."""
    return " ".join(str(value).split()).replace("|", "\\|")


def _short(value: Any, limit: int = 60) -> str:
    """One-line excerpt."""
    text = " ".join(str(value).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _date(stamp: float) -> str:
    return time.strftime("%Y-%m-%d", time.localtime(stamp)) if stamp else "-"


def _meta(payload: dict[str, Any]) -> str:
    """Status, revision, drift, and readiness line."""
    plan = payload.get("plan") or {}
    bits = [f"**Status:** {plan.get('status', '-')}"]
    approval = payload.get("approval") or {}
    revision = int(approval.get("revision", 0) or 0)
    if revision:
        bits.append(
            f"**Revision:** r{revision} "
            f"({_date(float(approval.get('approved_at', 0) or 0))}, "
            f"@{approval.get('actor', '')})"
        )
        bits.append(f"**Drift:** {approval.get('drift', 0)} changes")
    readiness = payload.get("readiness") or {}
    bits.append(f"**Readiness:** {'ready' if readiness.get('ready') else 'not ready'}")
    return " · ".join(bits)


def _criteria(payload: dict[str, Any]) -> list[str]:
    """Acceptance table for plan, milestone, and task criteria."""
    lines = [
        "## Acceptance criteria",
        "",
        "| Criterion | Done | Proving tasks | Commits | PRs | Evidence |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for criterion in payload.get("criteria", []):
        tasks = criterion.get("tasks", [])
        task_text = ", ".join(f"T{task['id']}" for task in tasks) or "-"
        lines.append(
            f"| {_cell(criterion.get('text', ''))} | "
            f"{'yes' if criterion.get('done') else 'no'} | "
            f"{task_text} | {len(criterion.get('commits', []))} | "
            f"{len(criterion.get('prs', []))} | {criterion.get('evidence', 'none')} |"
        )
    return lines


def _work(payload: dict[str, Any]) -> list[str]:
    """Milestones and tasks with status."""
    lines = ["## Milestones and tasks", ""]
    for milestone in payload.get("milestones", []):
        tasks = milestone.get("tasks", [])
        done = sum(1 for task in tasks if task.get("status") == "done")
        lines.append(
            f"### M{milestone['id']} {_cell(milestone.get('title', ''))} "
            f"({milestone.get('status', '-')}, {done}/{len(tasks)})"
        )
        for task in tasks:
            mark = "x" if task.get("status") == "done" else " "
            lines.append(f"- [{mark}] T{task['id']} {_cell(task.get('title', ''))}")
        lines.append("")
    return lines


def _provenance(payload: dict[str, Any]) -> list[str]:
    """Commits and pull requests."""
    lines = ["## Commits", ""]
    commits = payload.get("commits", [])
    if not commits:
        lines.append("none linked")
    for commit in commits:
        sha = str(commit.get("sha", ""))[:12]
        link = f" ([link]({commit['url']}))" if commit.get("url") else ""
        lines.append(f"- `{sha}` {_short(commit.get('subject', ''))}{link}")
    lines.extend(["", "## Pull requests", ""])
    pulls = payload.get("prs", [])
    if not pulls:
        lines.append("none linked")
    for pull in pulls:
        link = f" ([link]({pull['url']}))" if pull.get("url") else ""
        lines.append(
            f"- #{pull.get('number')} {_short(pull.get('title', ''))} "
            f"({pull.get('state', 'unknown')}){link}"
        )
    return lines


def _findings(payload: dict[str, Any]) -> list[str]:
    """Lint findings and the audit summary."""
    lines = ["## Findings", ""]
    findings = payload.get("lint", [])
    if not findings:
        lines.append("- lint: clean")
    for finding in findings:
        lines.append(
            f"- lint {finding.get('severity', '')} {finding.get('rule', '')}: "
            f"{_short(finding.get('message', ''))}"
        )
    report = payload.get("audit") or {}
    lines.append(
        f"- audit: coverage {float(report.get('coverage', 1.0)):.0%} · "
        f"trace {float(report.get('trace_coverage', 1.0)):.0%} · "
        f"evidence {float(report.get('evidence_coverage', 1.0)):.0%}"
    )
    return lines


def _questions(payload: dict[str, Any]) -> list[str]:
    """Open questions, numbered by id."""
    lines = ["## Open questions", ""]
    questions = payload.get("questions", [])
    if not questions:
        lines.append("none")
    for question in questions:
        lines.append(f"{question['id']}. Q{question['id']}: {_cell(question.get('text', ''))}")
    return lines


def _notes(payload: dict[str, Any]) -> list[str]:
    """Recent plan notes."""
    notes = payload.get("notes", [])
    if not notes:
        return []
    lines = ["## Notes and follow-ups", ""]
    for note in notes:
        lines.append(f"- @{note.get('actor', '')}: {_short(note.get('text', ''), 120)}")
    return lines


def render(payload: dict[str, Any], max_chars: int = 0) -> str:
    """Render one deterministic Markdown packet."""
    plan = payload.get("plan") or {}
    lines = [f"# P{plan.get('id')} — {_cell(plan.get('name', ''))}", "", _meta(payload), ""]
    why = str(payload.get("why", "") or "").strip()
    what = str(payload.get("what", "") or "").strip()
    if why:
        lines.extend(["## Why", "", why, ""])
    if what:
        lines.extend(["## What", "", what, ""])
    lines.extend(_criteria(payload))
    lines.append("")
    lines.extend(_work(payload))
    lines.extend(_provenance(payload))
    lines.append("")
    lines.extend(_findings(payload))
    lines.append("")
    lines.extend(_questions(payload))
    notes = _notes(payload)
    if notes:
        lines.append("")
        lines.extend(notes)
    text = "\n".join(lines).rstrip() + "\n"
    if max_chars and len(text) > max_chars:
        notice = f"\n\n[truncated to {max_chars} chars]\n"
        text = text[: max(0, max_chars - len(notice))].rstrip() + notice
    return text
