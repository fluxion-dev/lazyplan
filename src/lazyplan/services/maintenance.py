"""Maintenance use cases: report, archive, trim, vacuum, and snapshots."""

from __future__ import annotations

from ..core.policies.maintenance import DEFAULT_WINDOW_SECS, parse_window_secs
from ..core.ports.maintenance import (
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


def report(port: MaintenancePort) -> MaintenanceReport:
    """Per-table bytes, row counts, and the reclaimable estimate."""
    return port.report()


def trim(
    port: MaintenancePort,
    now: float | None = None,
    days: str | float | None = None,
    apply: bool = False,
) -> TrimResult:
    """Preview derived-row trims, or write them when *apply* is true."""
    return port.trim(now=now, window_secs=_window_secs(days), apply=apply)


def vacuum(port: MaintenancePort) -> VacuumResult:
    """Reclaim free pages and report the file size before and after."""
    return port.vacuum()
