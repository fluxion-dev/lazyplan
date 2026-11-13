"""The one-line attention strip above the preview."""

from __future__ import annotations

import time
from typing import Any, Protocol

from ....core.ports.coordination import CoordinationPort
from ....core.ports.insights import InsightsPort
from ....services import coordination
from ...shared.design import escape_markup


class ControlPort(InsightsPort, CoordinationPort, Protocol):
    """Read surface for the control strip."""


def _plural(count: int, singular: str, plural: str | None = None) -> str:
    """One counted noun with a simple plural."""
    if count == 1:
        return f"{count} {singular}"
    return f"{count} {plural or singular + 's'}"


def _strip(reasons: list[str]) -> str:
    """One plain attention line, or nothing when the row is clear."""
    return " · ".join(reasons)


def _plan_tasks(full: dict[str, Any]) -> list[dict[str, Any]]:
    return [task for entry in full.get("milestones", []) for task in entry.get("tasks", [])]


def _task_summary(tasks: list[dict[str, Any]], stamp: float) -> tuple[int, int]:
    """Blocked and stale-claim counts for a task group."""
    blocked = sum(1 for task in tasks if task.get("blocked"))
    claims = [claim for task in tasks if isinstance(claim := task.get("claim"), dict)]
    stale = sum(1 for claim in claims if float(claim.get("expires_at") or 0) <= stamp)
    return blocked, stale


def _plan_strip(_store: ControlPort, _oid: int, full: dict[str, Any]) -> str:
    """Plan attention: open questions, drift, blocked work, and stale claims."""
    stamp = time.time()
    approval = full.get("approval") or {}
    questions = [
        question for question in full.get("questions", []) if question.get("status") == "open"
    ]
    blocked, stale = _task_summary(_plan_tasks(full), stamp)
    reasons: list[str] = []
    drift = int(approval.get("drift", 0) or 0)
    if drift:
        reasons.append(_plural(drift, "change") + " since approval")
    if questions:
        reasons.append(_plural(len(questions), "open question"))
    if blocked:
        reasons.append(_plural(blocked, "blocked task"))
    if stale:
        reasons.append(_plural(stale, "stale claim"))
    return _strip(reasons)


def _milestone_strip(_store: ControlPort, _oid: int, full: dict[str, Any]) -> str:
    """Milestone attention from its task rows."""
    stamp = time.time()
    tasks = [entry.get("task", {}) for entry in full.get("tasks", [])]
    blocked, stale = _task_summary(tasks, stamp)
    reasons: list[str] = []
    if blocked:
        reasons.append(_plural(blocked, "blocked task"))
    if stale:
        reasons.append(_plural(stale, "stale claim"))
    return _strip(reasons)


def _task_strip(store: ControlPort, oid: int, full: dict[str, Any]) -> str:
    """Task attention: blocked, open criteria, failing evidence, and overlap."""
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
        reasons.append(f"blocked {reason}".rstrip())
    if open_criteria:
        reasons.append(_plural(len(open_criteria), "open criterion", "open criteria"))
    if failing:
        reasons.append(_plural(len(failing), "failing check"))
    if overlaps:
        reasons.append(_plural(len(overlaps), "overlap"))
    return _strip(reasons)


def build_control_strip(store: ControlPort, kind: str, oid: int, full: dict[str, Any]) -> str:
    """One attention line for the selected plan, milestone, or task."""
    if kind == "plan":
        return _plan_strip(store, oid, full)
    if kind == "milestone":
        return _milestone_strip(store, oid, full)
    return _task_strip(store, oid, full)
