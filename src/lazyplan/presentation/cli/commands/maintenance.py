"""Maintenance CLI commands."""

from __future__ import annotations

import argparse
import sys

from lazyplan import services

from ....core.errors import MaintenanceBackupError, MaintenanceBusy
from ....core.ports.maintenance import (
    ArchiveResult,
    MaintenanceReport,
    RestoreResult,
    TrimResult,
    VacuumResult,
)
from ...shared import porcelain
from ...shared.design import msg_error
from ..emit import _emit_read


def _state(applied: bool) -> str:
    """Porcelain status for a preview or a write."""
    return "applied" if applied else "preview"


def _report_rows(report: MaintenanceReport) -> list[str]:
    """One summary row plus one row per table."""
    rows = [
        porcelain.row(
            "maint",
            "report",
            report.method,
            report.total_bytes,
            report.free_bytes,
            report.reclaimable_bytes,
        )
    ]
    rows.extend(
        porcelain.row("maint-table", row.table, row.bytes, row.rows) for row in report.tables
    )
    return rows


def _report_text(report: MaintenanceReport) -> str:
    lines = [
        f"method     {report.method}",
        f"total      {report.total_bytes} bytes",
        f"free       {report.free_bytes} bytes",
        f"reclaim    {report.reclaimable_bytes} bytes",
    ]
    for row in report.tables:
        lines.append(f"  {row.table:<24} {row.bytes:>10} bytes {row.rows:>8} rows")
    return "\n".join(lines)


def _archive_rows(result: ArchiveResult) -> list[str]:
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


def _archive_text(result: ArchiveResult) -> str:
    verb = "archived" if result.applied else "would archive"
    lines = [f"{verb} {len(result.plans)} plan(s) and {len(result.sessions)} session(s)"]
    if result.plans:
        lines.append("  plans    " + ", ".join(f"P{plan_id}" for plan_id in result.plans))
    if result.sessions:
        lines.append("  sessions " + ", ".join(f"S{sid}" for sid in result.sessions))
    return "\n".join(lines)


def _trim_rows(result: TrimResult) -> list[str]:
    state = _state(result.applied)
    return [
        porcelain.row("maint-trim", row.table, state, row.rows, "-", "-") for row in result.tables
    ]


def _trim_text(result: TrimResult) -> str:
    verb = "trimmed" if result.applied else "would trim"
    lines = [f"{verb} {result.total_rows} derived row(s)"]
    lines.extend(f"  {row.table:<24} {row.rows:>8}" for row in result.tables if row.rows)
    return "\n".join(lines)


def _vacuum_rows(result: VacuumResult) -> list[str]:
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


def _vacuum_text(result: VacuumResult) -> str:
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


def _cmd_maint_report(store: object, args: argparse.Namespace, actor: str) -> int:
    del actor
    report = services.maintenance.report(store)  # type: ignore[arg-type]
    return _emit_read(args, report.to_dict(), _report_rows(report), _report_text(report))


def _cmd_maint_archive(store: object, args: argparse.Namespace, actor: str) -> int:
    try:
        result = services.maintenance.archive(
            store,  # type: ignore[arg-type]
            days=args.days,
            apply=bool(args.apply),
            actor=actor,
        )
    except (MaintenanceBusy, MaintenanceBackupError) as exc:
        print(msg_error(exc), file=sys.stderr)
        return 1
    except ValueError as exc:
        print(msg_error(exc), file=sys.stderr)
        return 2
    return _emit_read(args, result.to_dict(), _archive_rows(result), _archive_text(result))


def _cmd_maint_restore(store: object, args: argparse.Namespace, actor: str) -> int:
    try:
        result = services.maintenance.restore(
            store,  # type: ignore[arg-type]
            plan_id=args.plan,
            session_id=args.session,
            actor=actor,
        )
    except KeyError as exc:
        print(msg_error(exc), file=sys.stderr)
        return 1
    except ValueError as exc:
        print(msg_error(exc), file=sys.stderr)
        return 1
    return _restore_emit(args, result)


def _restore_emit(args: argparse.Namespace, result: RestoreResult) -> int:
    row = porcelain.row("maint-restore", f"{result.kind}:{result.id}", "restored", "-", "-", "-")
    return _emit_read(
        args,
        result.to_dict(),
        [row],
        f"restored {result.kind} #{result.id}",
    )


def _cmd_maint_trim(store: object, args: argparse.Namespace, actor: str) -> int:
    del actor
    try:
        result = services.maintenance.trim(
            store,  # type: ignore[arg-type]
            days=args.days,
            apply=bool(args.apply),
        )
    except (MaintenanceBusy, MaintenanceBackupError) as exc:
        print(msg_error(exc), file=sys.stderr)
        return 1
    except ValueError as exc:
        print(msg_error(exc), file=sys.stderr)
        return 2
    return _emit_read(args, result.to_dict(), _trim_rows(result), _trim_text(result))


def _cmd_maint_vacuum(store: object, args: argparse.Namespace, actor: str) -> int:
    del actor
    try:
        result = services.maintenance.vacuum(store, apply=bool(args.apply))  # type: ignore[arg-type]
    except (MaintenanceBusy, MaintenanceBackupError) as exc:
        print(msg_error(exc), file=sys.stderr)
        return 1
    return _emit_read(args, result.to_dict(), _vacuum_rows(result), _vacuum_text(result))
