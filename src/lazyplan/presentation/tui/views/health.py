"""Health sections shared by the detail page."""

from __future__ import annotations

import time
from typing import Any, cast

from .... import services
from ....core.ports.insights import InsightsPort
from ....core.ports.provenance import ProvenancePort
from ...shared.design import EMPTY_APPROVAL, SECTION_ICON, escape_markup


def _heading(key: str, label: str) -> str:
    """One section heading with its icon."""
    icon = SECTION_ICON.get(key, "")
    return f"[bold cyan]{icon}[/] [bold]{label}[/]" if icon else f"[bold]{label}[/]"


def read_approval(lines: list[str], kind: str, full: dict[str, Any]) -> None:
    """Approval revision, policy, and drift for a plan."""
    if kind != "plan":
        return
    approval = full.get("approval")
    if not approval:
        return
    revision = int(approval.get("revision", 0) or 0)
    if not revision:
        lines.extend(["", _heading("approval", "approval"), f"  [dim]{EMPTY_APPROVAL}[/]"])
        return
    flags = " · enforced" if approval.get("enforced") else ""
    stamp = float(approval.get("approved_at", 0) or 0)
    day = time.strftime("%Y-%m-%d", time.localtime(stamp)) if stamp else "-"
    lines.extend(["", _heading("approval", f"approval r{revision}{flags}")])
    lines.append(f"  [dim]{day}[/] @{escape_markup(str(approval.get('actor', '')))}")
    reason = str(approval.get("reason", "") or "").strip()
    if reason:
        lines.append(f"  {escape_markup(reason)}")
    drift = int(approval.get("drift", 0) or 0)
    if drift:
        lines.append(f"  [yellow]Δ {drift} changes since approval[/]")
        for item in (approval.get("recent") or [])[:3]:
            field = str(item.get("field") or item.get("action") or "")
            why = str(item.get("reason") or "").strip()
            suffix = f" · {escape_markup(why)}" if why else ""
            lines.append(f"    [dim]{escape_markup(field)}[/]{suffix}")


def read_readiness(lines: list[str], store: ProvenancePort, kind: str, oid: int) -> None:
    """Lint, criterion coverage, and question readiness for a plan."""
    if kind != "plan":
        return
    try:
        result = services.plan_ready(cast(InsightsPort, store), oid)
    except Exception:
        return
    if result is None:
        return
    if result.ready:
        lines.extend(["", _heading("ready", "ready"), "  [green]✓ ready[/]"])
        return
    failed = [check for check in result.checks if not check.ok]
    lines.extend(["", _heading("ready", f"ready · {len(failed)} failing")])
    for check in result.checks:
        mark = "[green]✓[/]" if check.ok else "[yellow]✗[/]"
        lines.append(f"  {mark} [dim]{check.id}[/] {escape_markup(check.detail)}")


def _task_rows(kind: str, full: dict[str, Any]) -> list[dict[str, Any]]:
    if kind == "plan":
        return [task for entry in full.get("milestones", []) for task in entry.get("tasks", [])]
    if kind == "milestone":
        return [entry.get("task", {}) for entry in full.get("tasks", [])]
    return []


def read_claims(lines: list[str], kind: str, full: dict[str, Any]) -> None:
    """Active and stale claims rolled up from child tasks."""
    if kind == "task":
        return
    stamp = time.time()
    claims = [
        (task, claim)
        for task in _task_rows(kind, full)
        if isinstance(claim := task.get("claim"), dict)
    ]
    if not claims:
        return
    active = sum(1 for _task, claim in claims if float(claim.get("expires_at") or 0) > stamp)
    lines.extend(["", _heading("claims", f"claims {len(claims)} · {active} active")])
    for task, claim in claims[:3]:
        expires = float(claim.get("expires_at") or 0)
        state = "active" if expires > stamp else "stale"
        lines.append(
            f"  [dim]◉[/] @{escape_markup(str(claim.get('actor', '')))} · "
            f"[dim]T{task.get('id')}[/] {escape_markup(str(task.get('title', '')))} ({state})"
        )
    if len(claims) > 3:
        lines.append(f"  [dim]+{len(claims) - 3} more[/]")


def read_coverage(lines: list[str], kind: str, full: dict[str, Any]) -> None:
    """Evidence coverage across the plan criteria."""
    if kind != "plan":
        return
    criteria = full.get("criteria", [])
    if not criteria:
        return
    if not any((criterion.get("evidence") or {}).get("count") for criterion in criteria):
        return
    proven = sum(
        1 for criterion in criteria if (criterion.get("evidence") or {}).get("state") == "pass"
    )
    lines.extend(["", _heading("coverage", f"evidence {proven}/{len(criteria)}")])


def _plan_id_for(store: ProvenancePort, kind: str, oid: int, obj: dict[str, Any]) -> int | None:
    if kind == "plan":
        return oid
    if kind == "milestone":
        return int(obj.get("plan_id") or 0) or None
    milestone = store.get_milestone(int(obj.get("milestone_id", 0)))
    return milestone.plan_id if milestone is not None else None


def read_handoff(
    lines: list[str], store: ProvenancePort, kind: str, oid: int, obj: dict[str, Any]
) -> None:
    """The previous session's summary and handoff for the owning plan."""
    plan_id = _plan_id_for(store, kind, oid, obj)
    try:
        session = services.previous_session(cast(InsightsPort, store), plan_id=plan_id)
    except Exception:
        return
    if not session:
        return
    lines.extend(["", _heading("session", f"session S{session['id']} @{session['actor']}")])
    if session.get("summary"):
        lines.append(f"  [dim]summary[/] {escape_markup(str(session['summary']))}")
    if session.get("handoff"):
        lines.append(f"  [dim]handoff[/] {escape_markup(str(session['handoff']))}")
