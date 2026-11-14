"""Maintenance CLI commands."""

from __future__ import annotations

import argparse
import sys

from lazyplan import services

from ....core.errors import MaintenanceBackupError, MaintenanceBusy
from ...shared import maintenance_presenter as view
from ...shared.design import msg_error
from ..emit import _emit_read


def _cmd_maint_report(store: object, args: argparse.Namespace, actor: str) -> int:
    del actor
    try:
        report = services.maintenance.report(store, days=args.days)  # type: ignore[arg-type]
    except ValueError as exc:
        print(msg_error(exc), file=sys.stderr)
        return 2
    return _emit_read(
        args, view.report_payload(report), view.report_rows(report), view.report_text(report)
    )


def _maint_error(exc: Exception) -> int:
    """Exit code for one maintenance failure: busy/backup 1, bad input 2."""
    print(msg_error(exc), file=sys.stderr)
    return 1 if isinstance(exc, (MaintenanceBusy, MaintenanceBackupError)) else 2


def _days_action(store: object, args: argparse.Namespace, actor: str, action: str) -> int:
    """Archive or trim with the shared days/apply flags and payload views."""
    if action == "archive":
        try:
            archived = services.maintenance.archive(
                store,  # type: ignore[arg-type]
                days=args.days,
                apply=bool(args.apply),
                actor=actor,
            )
        except (MaintenanceBusy, MaintenanceBackupError, ValueError) as exc:
            return _maint_error(exc)
        return _emit_read(
            args,
            view.archive_payload(archived),
            view.archive_rows(archived),
            view.archive_text(archived),
        )
    try:
        trimmed = services.maintenance.trim(
            store,  # type: ignore[arg-type]
            days=args.days,
            apply=bool(args.apply),
            actor=actor,
        )
    except (MaintenanceBusy, MaintenanceBackupError, ValueError) as exc:
        return _maint_error(exc)
    return _emit_read(
        args, view.trim_payload(trimmed), view.trim_rows(trimmed), view.trim_text(trimmed)
    )


def _cmd_maint_archive(store: object, args: argparse.Namespace, actor: str) -> int:
    return _days_action(store, args, actor, "archive")


def _cmd_maint_trim(store: object, args: argparse.Namespace, actor: str) -> int:
    return _days_action(store, args, actor, "trim")


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
    return _emit_read(
        args, view.restore_payload(result), view.restore_rows(result), view.restore_text(result)
    )


def _cmd_maint_vacuum(store: object, args: argparse.Namespace, actor: str) -> int:
    try:
        result = services.maintenance.vacuum(
            store,  # type: ignore[arg-type]
            apply=bool(args.apply),
            actor=actor,
        )
    except (MaintenanceBusy, MaintenanceBackupError) as exc:
        print(msg_error(exc), file=sys.stderr)
        return 1
    return _emit_read(
        args, view.vacuum_payload(result), view.vacuum_rows(result), view.vacuum_text(result)
    )
