"""One maintenance presenter for the CLI, MCP, and the screen.

Payloads stay the dataclass shapes; rows and text are pure formatting over
those dataclasses, so no surface re-implements window parsing or field names.
"""

from __future__ import annotations

from ...core.ports.maintenance import (
    ArchiveResult,
    MaintenanceReport,
    RestoreResult,
    TrimResult,
    VacuumResult,
)
from . import porcelain


def _state(applied: bool) -> str:
    """Porcelain status for a preview or a write."""
    return "applied" if applied else "preview"


def report_payload(report: MaintenanceReport) -> dict:
    return report.to_dict()


def archive_payload(result: ArchiveResult) -> dict:
    return result.to_dict()


def trim_payload(result: TrimResult) -> dict:
    return result.to_dict()


def vacuum_payload(result: VacuumResult) -> dict:
    return result.to_dict()


def restore_payload(result: RestoreResult) -> dict:
    return result.to_dict()


def report_rows(report: MaintenanceReport) -> list[str]:
    """One summary row plus one row per table."""
    rows = [
        porcelain.row(
            "maint",
            "report",
            report.method,
            report.used_bytes,
            report.free_bytes,
            f"{report.reclaimable_bytes} file={report.file_bytes} window={report.window_days}d",
        )
    ]
    rows.extend(
        porcelain.row("maint-table", row.table, row.bytes, row.rows) for row in report.tables
    )
    return rows


def report_text(report: MaintenanceReport) -> str:
    lines = [
        f"method     {report.method}",
        f"used       {report.used_bytes} bytes",
        f"file       {report.file_bytes} bytes",
        f"free       {report.free_bytes} bytes",
        f"reclaim    {report.reclaimable_bytes} bytes ({report.window_days:g}-day window)",
    ]
    for row in report.tables:
        lines.append(f"  {row.table:<24} {row.bytes:>10} bytes {row.rows:>8} rows")
    return "\n".join(lines)


def archive_rows(result: ArchiveResult) -> list[str]:
    state = _state(result.applied)
    rows = [
        porcelain.row("maint-archive", f"plan:{plan_id}", state, "-", "-", "-")
        for plan_id in result.plans
    ]
    rows.extend(
        porcelain.row("maint-archive", f"session:{session_id}", state, "-", "-", "-")
        for session_id in result.sessions
    )
    return rows


def archive_text(result: ArchiveResult) -> str:
    verb = "archived" if result.applied else "would archive"
    lines = [f"{verb} {len(result.plans)} plan(s) and {len(result.sessions)} session(s)"]
    if result.plans:
        lines.append("  plans    " + ", ".join(f"P{plan_id}" for plan_id in result.plans))
    if result.sessions:
        lines.append("  sessions " + ", ".join(f"S{sid}" for sid in result.sessions))
    return "\n".join(lines)


def trim_rows(result: TrimResult) -> list[str]:
    state = _state(result.applied)
    return [
        porcelain.row("maint-trim", row.table, state, row.rows, "-", "-") for row in result.tables
    ]


def trim_text(result: TrimResult) -> str:
    verb = "trimmed" if result.applied else "would trim"
    lines = [f"{verb} {result.total_rows} derived row(s)"]
    lines.extend(f"  {row.table:<24} {row.rows:>8}" for row in result.tables if row.rows)
    return "\n".join(lines)


def trim_counts(result: TrimResult) -> dict[str, int]:
    """Candidate rows per table, used by the screen and parity checks."""
    return {row.table: row.rows for row in result.tables}


def vacuum_rows(result: VacuumResult) -> list[str]:
    return [
        porcelain.row(
            "maint-vacuum",
            "database",
            _state(result.applied),
            result.before_bytes,
            result.after_bytes,
            f"{result.before_free_pages}->{result.after_free_pages}",
        )
    ]


def vacuum_text(result: VacuumResult) -> str:
    if not result.applied:
        return (
            f"preview  {result.before_bytes} bytes with {result.before_free_pages} free page(s); "
            "add --apply to reclaim"
        )
    return (
        f"vacuumed {result.before_bytes} -> {result.after_bytes} bytes "
        f"(freed {result.freed_bytes}); free pages "
        f"{result.before_free_pages} -> {result.after_free_pages}"
    )


def restore_rows(result: RestoreResult) -> list[str]:
    return [porcelain.row("maint-restore", f"{result.kind}:{result.id}", "restored", "-", "-", "-")]


def restore_text(result: RestoreResult) -> str:
    return f"restored {result.kind} #{result.id}"
