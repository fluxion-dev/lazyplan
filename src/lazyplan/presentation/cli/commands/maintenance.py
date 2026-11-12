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
    return _emit_read(
        args, view.archive_payload(result), view.archive_rows(result), view.archive_text(result)
    )


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


def _cmd_maint_trim(store: object, args: argparse.Namespace, actor: str) -> int:
    try:
        result = services.maintenance.trim(
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
    return _emit_read(
        args, view.trim_payload(result), view.trim_rows(result), view.trim_text(result)
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
