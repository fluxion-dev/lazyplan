"""The one-line attention strip above the preview."""

from __future__ import annotations

import time
from typing import Any, Protocol

from ....core.ports.coordination import CoordinationPort
from ....core.ports.insights import InsightsPort
from ....services import coordination
from ...shared.design import escape_markup, status_word


class ControlPort(InsightsPort, CoordinationPort, Protocol):
    """Read surface for the control strip."""


def _plural(count: int, singular: str, plural: str | None = None) -> str:
    """One counted noun with a simple plural."""
    if count == 1:
        return f"{count} {singular}"
    return f"{count} {plural or singular + 's'}"


def _strip(reasons: list[str], suffix: str = "") -> str:
    """One attention line: clear or review, then the quiet context."""
    head = "[bold]attention[/]  "
    body = "[yellow]⚠ review[/] · " + " · ".join(reasons) if reasons else "[green]✓ clear[/]"
    if suffix:
        body += f" · [dim]{suffix}[/]"
    return head + body


def _approval(revision: int, drift: int, enforced: bool) -> tuple[str, bool]:
    """Approval reason and suffix; the drift count is an attention reason."""
    if not revision:
        return "[dim]unapproved[/]", False
    flags = " enforced" if enforced else ""
    suffix = f"r{revision}{flags}"
    if drift:
        return f"[yellow]Δ{drift} drift[/]", True
    return f"[green]✓ in sync[/] · [dim]{suffix}[/]", False


def _plan_tasks(full: dict[str, Any]) -> list[dict[str, Any]]:
    return [task for entry in full.get("milestones", []) for task in entry.get("tasks", [])]


def _task_summary(tasks: list[dict[str, Any]], stamp: float) -> tuple[int, list[dict], int, int]:
    """Blocked, claim, stale-claim, and doing counts for a task group."""
    blocked = sum(1 for task in tasks if task.get("blocked"))
    claims = [claim for task in tasks if isinstance(claim := task.get("claim"), dict)]
    stale = sum(1 for claim in claims if float(claim.get("expires_at") or 0) <= stamp)
    doing = sum(1 for task in tasks if task.get("status") == "doing")
    return blocked, claims, stale, doing


def _plan_strip(_store: ControlPort, _oid: int, full: dict[str, Any]) -> str:
    """Plan attention: open questions, drift, blocked work, and stale claims."""
    stamp = time.time()
    approval = full.get("approval") or {}
    questions = [
        question for question in full.get("questions", []) if question.get("status") == "open"
    ]
    tasks = _plan_tasks(full)
    blocked, _claims, stale, _doing = _task_summary(tasks, stamp)
    reasons: list[str] = []
    approval_text, drift = _approval(
        int(approval.get("revision", 0) or 0),
        int(approval.get("drift", 0) or 0),
        bool(approval.get("enforced")),
    )
    if drift:
        reasons.append(approval_text)
    if questions:
        reasons.append(f"[yellow]{_plural(len(questions), 'question')}[/]")
    if blocked:
        reasons.append(f"[yellow]{_plural(blocked, 'blocked')}[/]")
    if stale:
        reasons.append(f"[yellow]{_plural(stale, 'stale claim')}[/]")
    return _strip(reasons)


def _milestone_strip(_store: ControlPort, _oid: int, full: dict[str, Any]) -> str:
    """Milestone attention from its task rows."""
    stamp = time.time()
    tasks = [entry.get("task", {}) for entry in full.get("tasks", [])]
    blocked, claims, stale, doing = _task_summary(tasks, stamp)
    reasons: list[str] = []
    if blocked:
        reasons.append(f"[yellow]{_plural(blocked, 'blocked')}[/]")
    if stale:
        reasons.append(f"[yellow]{_plural(stale, 'stale claim')}[/]")
    suffix = f"{_plural(doing, 'doing task')} · {_plural(len(tasks), 'task')}"
    if claims:
        suffix += f" · {_plural(len(claims), 'claim')}"
    return _strip(reasons, suffix)


def _task_strip(store: ControlPort, oid: int, full: dict[str, Any]) -> str:
    """Task attention: blocked, open criteria, failing evidence, and overlap."""
    stamp = time.time()
    task = full.get("task", {})
    criteria = full.get("criteria", [])
    open_criteria = [criterion for criterion in criteria if not criterion.get("done")]
    failing = [
        criterion
        for criterion in criteria
        if (criterion.get("evidence") or {}).get("state") == "fail"
    ]
    overlaps: list[dict] = []
    if task.get("claim") or full.get("touchpoints"):
        try:
            overlaps = coordination.overlaps(store, oid)
        except Exception:
            overlaps = []
    reasons: list[str] = []
    if task.get("blocked"):
        reason = escape_markup(str(task.get("blocked_reason") or ""))
        reasons.append(f"[red]blocked[/] {reason}".rstrip())
    if open_criteria:
        reasons.append(f"[yellow]{_plural(len(open_criteria), 'criterion', 'criteria')}[/]")
    if failing:
        reasons.append(f"[red]{_plural(len(failing), 'failing')}[/]")
    if overlaps:
        reasons.append(f"[yellow]{_plural(len(overlaps), 'overlap')}[/]")
    claim = task.get("claim")
    suffix = status_word(str(task.get("status", "")), "plain")
    if isinstance(claim, dict):
        expires = float(claim.get("expires_at") or 0)
        marker = "stale " if expires and expires <= stamp else ""
        suffix += f" · {marker}claim @{escape_markup(str(claim.get('actor') or ''))}"
    return _strip(reasons, suffix)


def build_control_strip(store: ControlPort, kind: str, oid: int, full: dict[str, Any]) -> str:
    """One attention line for the selected plan, milestone, or task."""
    if kind == "plan":
        return _plan_strip(store, oid, full)
    if kind == "milestone":
        return _milestone_strip(store, oid, full)
    return _task_strip(store, oid, full)
