"""Maintenance use cases: report, archive, trim, vacuum, and snapshots."""

from __future__ import annotations

import time

from ..core.policies.maintenance import (
    DEFAULT_WINDOW_SECS,
    parse_window_secs,
    plan_archive_candidates,
    session_archive_candidates,
)
from ..core.ports.maintenance import (
    ArchiveResult,
    BackupResult,
    MaintenancePort,
    MaintenanceReport,
    RestoreResult,
    TrimResult,
    VacuumResult,
)


def _window_secs(days: str | float | None) -> float:
    """One-week default, or the explicit day window for this run."""
    if days is None:
        return DEFAULT_WINDOW_SECS
    return parse_window_secs(str(days))


def _snapshot(port: MaintenancePort, apply: bool, label: str = "") -> BackupResult | None:
    """Snapshot before a write; previews never create one."""
    if not apply:
        return None
    return port.backup(label)


def report(port: MaintenancePort, days: str | float | None = None) -> MaintenanceReport:
    """Per-table bytes, row counts, and the reclaimable estimate for one window."""
    return port.report(window_secs=_window_secs(days))


def _archive_candidates(
    port: MaintenancePort, stamp: float, window: float
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """Plan and session ids past the window, in store order."""
    plans = plan_archive_candidates(
        port.list_plans(archived="hide"),
        port.plan_status_events_map(),
        stamp,
        window,
    )
    sessions = session_archive_candidates(
        port.list_sessions(archived="hide", limit=1_000_000),
        stamp,
        window,
    )
    return tuple(plan.id for plan in plans), tuple(session.id for session in sessions)


def _write_archive(
    port: MaintenancePort,
    stamp: float,
    window: float,
    actor: str,
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """Snapshot, then re-check and archive both kinds in one transaction."""
    _snapshot(port, True, "archive")
    with port.transaction():
        plan_ids, session_ids = _archive_candidates(port, stamp, window)
        for plan_id in plan_ids:
            port.archive_plan(plan_id, actor=actor, now=stamp)
        if session_ids:
            port.archive_sessions(session_ids, actor=actor, now=stamp)
    return plan_ids, session_ids


def archive(
    port: MaintenancePort,
    now: float | None = None,
    days: str | float | None = None,
    apply: bool = False,
    actor: str = "human",
) -> ArchiveResult:
    """Preview plans and sessions past the window, or archive them with *apply*."""
    stamp = time.time() if now is None else now
    window = _window_secs(days)
    plan_ids, session_ids = _archive_candidates(port, stamp, window)
    if apply:
        plan_ids, session_ids = _write_archive(port, stamp, window, actor)
        port.log(
            actor,
            "maintenance",
            "archive",
            f"archived {len(plan_ids)} plan(s) and {len(session_ids)} session(s)",
        )
    return ArchiveResult(plans=plan_ids, sessions=session_ids, applied=apply)


def trim(
    port: MaintenancePort,
    now: float | None = None,
    days: str | float | None = None,
    apply: bool = False,
    actor: str = "human",
) -> TrimResult:
    """Preview derived-row trims, or snapshot and write them with *apply*."""
    window = _window_secs(days)
    _snapshot(port, apply, "trim")
    result = port.trim(now=now, window_secs=window, apply=apply)
    if apply:
        port.log(actor, "maintenance", "trim", f"trimmed {result.total_rows} derived row(s)")
    return result


def vacuum(port: MaintenancePort, apply: bool = False, actor: str = "human") -> VacuumResult:
    """Preview free pages, or snapshot and vacuum with *apply*."""
    if not apply:
        return port.vacuum_preview()
    _snapshot(port, True, "vacuum")
    result = port.vacuum()
    port.log(
        actor,
        "maintenance",
        "vacuum",
        f"vacuumed {result.before_bytes} -> {result.after_bytes} bytes",
    )
    return result


def restore(
    port: MaintenancePort,
    plan_id: int | None = None,
    session_id: int | None = None,
    actor: str = "human",
) -> RestoreResult:
    """Return one archived plan or session to the default views."""
    if (plan_id is None) == (session_id is None):
        raise ValueError("restore needs exactly one of plan or session")
    if plan_id is not None:
        if port.get_plan(plan_id) is None:
            raise KeyError(f"plan {plan_id} not found")
        if not port.restore_plan(plan_id, actor=actor):
            raise ValueError(f"plan {plan_id} is not archived")
        return RestoreResult("plan", plan_id, True)
    assert session_id is not None
    if port.get_session(session_id) is None:
        raise KeyError(f"session {session_id} not found")
    if not port.restore_session(session_id, actor=actor):
        raise ValueError(f"session {session_id} is not archived")
    return RestoreResult("session", session_id, True)
