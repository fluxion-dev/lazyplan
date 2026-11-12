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


def report(port: MaintenancePort) -> MaintenanceReport:
    """Per-table bytes, row counts, and the reclaimable estimate."""
    return port.report()


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
    plan_ids: tuple[int, ...],
    session_ids: tuple[int, ...],
    stamp: float,
    actor: str,
) -> None:
    """Snapshot, then archive both kinds in one transaction."""
    _snapshot(port, True, "archive")
    with port.transaction():
        for plan_id in plan_ids:
            port.archive_plan(plan_id, actor=actor, now=stamp)
        if session_ids:
            port.archive_sessions(session_ids, actor=actor, now=stamp)


def archive(
    port: MaintenancePort,
    now: float | None = None,
    days: str | float | None = None,
    apply: bool = False,
    actor: str = "human",
) -> ArchiveResult:
    """Preview plans and sessions past the window, or archive them with *apply*."""
    stamp = time.time() if now is None else now
    plan_ids, session_ids = _archive_candidates(port, stamp, _window_secs(days))
    if apply:
        _write_archive(port, plan_ids, session_ids, stamp, actor)
    return ArchiveResult(plans=plan_ids, sessions=session_ids, applied=apply)


def trim(
    port: MaintenancePort,
    now: float | None = None,
    days: str | float | None = None,
    apply: bool = False,
) -> TrimResult:
    """Preview derived-row trims, or snapshot and write them with *apply*."""
    _snapshot(port, apply, "trim")
    return port.trim(now=now, window_secs=_window_secs(days), apply=apply)


def vacuum(port: MaintenancePort, apply: bool = False) -> VacuumResult:
    """Preview free pages, or snapshot and vacuum with *apply*."""
    if not apply:
        return port.vacuum_preview()
    _snapshot(port, True, "vacuum")
    return port.vacuum()
