"""The two-line control strip above the preview."""

from __future__ import annotations

import time
from typing import Any, Protocol

from ....core.ports.coordination import CoordinationPort
from ....core.ports.insights import InsightsPort
from ....services import coordination, ready
from ...shared.design import escape_markup, status_word


class ControlPort(InsightsPort, CoordinationPort, Protocol):
    """Read surface for the control strip."""


def _plural(count: int, singular: str, plural: str | None = None) -> str:
    """One counted noun with a simple plural."""
    if count == 1:
        return f"{count} {singular}"
    return f"{count} {plural or singular + 's'}"


def _approval_line(approval: dict[str, Any]) -> str:
    """One compact approval and drift line."""
    revision = int(approval.get("revision", 0) or 0)
    if not revision:
        return "[dim]unapproved[/]"
    flags = " enforced" if approval.get("enforced") else ""
    drift = int(approval.get("drift", 0) or 0)
    if drift:
        return f"[yellow]Δ{drift} drift[/] · [dim]r{revision}{flags}[/]"
    return f"[green]✓ in sync[/] · [dim]r{revision}{flags}[/]"


def _claim_line(claim: dict[str, Any] | None, stamp: float) -> str:
    """Claim state with a stale marker."""
    if not claim:
        return "[dim]no claim[/]"
    actor = escape_markup(str(claim.get("actor") or ""))
    expires = float(claim.get("expires_at") or 0)
    if expires and expires <= stamp:
        return f"[yellow]stale claim @{actor}[/]"
    return f"[dim]claim @{actor}[/]"


def _readiness_line(store: ControlPort, plan_id: int) -> str:
    """Plan readiness in one label, or a calm unknown state."""
    try:
        result = ready.check(store, plan_id)
    except Exception:
        return "[dim]readiness unavailable[/]"
    if result is None:
        return "[dim]readiness unknown[/]"
    if result.ready:
        return "[green]✓ ready[/]"
    failed = sum(1 for check in result.checks if not check.ok)
    return f"[yellow]⚠ {_plural(failed, 'check')}[/]"


def _plan_tasks(full: dict[str, Any]) -> list[dict[str, Any]]:
    return [task for entry in full.get("milestones", []) for task in entry.get("tasks", [])]


def _needs_line(parts: list[str]) -> str:
    return "[bold]needs[/]  " + (" · ".join(parts) if parts else "[green]nothing needs you[/]")


def _plan_strip(store: ControlPort, oid: int, full: dict[str, Any]) -> str:
    """Plan health and the reasons it may need a human."""
    stamp = time.time()
    approval = full.get("approval") or {}
    questions = [
        question for question in full.get("questions", []) if question.get("status") == "open"
    ]
    tasks = _plan_tasks(full)
    blocked = sum(1 for task in tasks if task.get("blocked"))
    claims = [claim for task in tasks if isinstance(claim := task.get("claim"), dict)]
    stale = sum(1 for claim in claims if float(claim.get("expires_at") or 0) <= stamp)
    head = f"[bold]health[/]  {_readiness_line(store, oid)} · {_approval_line(approval)}"
    needs: list[str] = []
    if questions:
        needs.append(f"[yellow]{_plural(len(questions), 'open question')}[/]")
    if blocked:
        needs.append(f"[yellow]{_plural(blocked, 'blocked task')}[/]")
    if stale:
        needs.append(f"[yellow]{_plural(stale, 'stale claim')}[/]")
    if claims:
        needs.append(f"[dim]{_plural(len(claims), 'claim')}[/]")
    return f"{head}\n{_needs_line(needs)}"


def _milestone_strip(_store: ControlPort, _oid: int, full: dict[str, Any]) -> str:
    """Milestone health from its task rows."""
    stamp = time.time()
    tasks = [entry.get("task", {}) for entry in full.get("tasks", [])]
    blocked = sum(1 for task in tasks if task.get("blocked"))
    claims = [claim for task in tasks if isinstance(claim := task.get("claim"), dict)]
    stale = sum(1 for claim in claims if float(claim.get("expires_at") or 0) <= stamp)
    doing = sum(1 for task in tasks if task.get("status") == "doing")
    head = f"[bold]slice[/]  [dim]{_plural(doing, 'doing task')}[/] · {_plural(len(tasks), 'task')}"
    needs: list[str] = []
    if blocked:
        needs.append(f"[yellow]{_plural(blocked, 'blocked task')}[/]")
    if stale:
        needs.append(f"[yellow]{_plural(stale, 'stale claim')}[/]")
    if claims:
        needs.append(f"[dim]{_plural(len(claims), 'claim')}[/]")
    return f"{head}\n{_needs_line(needs)}"


def _task_strip(store: ControlPort, oid: int, full: dict[str, Any]) -> str:
    """Task health, claim, evidence, and overlap hints."""
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
    head = (
        f"[bold]work[/]  {status_word(str(task.get('status', '')), 'rich')}"
        f" · {_claim_line(task.get('claim'), stamp)}"
    )
    needs: list[str] = []
    if task.get("blocked"):
        reason = escape_markup(str(task.get("blocked_reason") or ""))
        needs.append(f"[red]blocked[/] {reason}".rstrip())
    if open_criteria:
        needs.append(f"[yellow]{_plural(len(open_criteria), 'open criterion', 'open criteria')}[/]")
    if failing:
        needs.append(f"[red]{_plural(len(failing), 'failing evidence')}[/]")
    if overlaps:
        needs.append(f"[yellow]{_plural(len(overlaps), 'overlap')}[/]")
    return f"{head}\n{_needs_line(needs)}"


def build_control_strip(store: ControlPort, kind: str, oid: int, full: dict[str, Any]) -> str:
    """Two-line control strip for the selected plan, milestone, or task."""
    if kind == "plan":
        return _plan_strip(store, oid, full)
    if kind == "milestone":
        return _milestone_strip(store, oid, full)
    return _task_strip(store, oid, full)
