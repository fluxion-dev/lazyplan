"""Maintenance use cases: report, archive, trim, vacuum, and snapshots."""

from __future__ import annotations

from ..core.ports.maintenance import MaintenancePort, MaintenanceReport


def report(port: MaintenancePort) -> MaintenanceReport:
    """Per-table bytes, row counts, and the reclaimable estimate."""
    return port.report()
