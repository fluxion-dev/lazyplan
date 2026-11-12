"""Argument group for maintenance commands."""

from __future__ import annotations

import argparse


def _apply_flag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--apply",
        action="store_true",
        help="write the change after a verified snapshot (default: preview only)",
    )


def _days_flag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--days",
        default=None,
        metavar="N|7.days",
        help="window for plans, sessions, and events (default: 7 days)",
    )


def add_maintenance_group(
    sub: argparse._SubParsersAction[argparse.ArgumentParser], common: argparse.ArgumentParser
) -> None:
    """`lpui maint`: report, archive, restore, trim, and vacuum."""
    group = sub.add_parser(
        "maint",
        help="report, archive, restore, trim, and vacuum the database",
        parents=[common],
    )
    group.set_defaults(noun_group="maint")
    actions = group.add_subparsers(
        dest="action",
        required=True,
        metavar="ACTION",
        title="maint actions",
        help="what to do with the database",
    )
    report = actions.add_parser(
        "report", help="show bytes and row counts per table", parents=[common]
    )
    _days_flag(report)
    archive = actions.add_parser(
        "archive", help="archive done plans and ended sessions", parents=[common]
    )
    _days_flag(archive)
    _apply_flag(archive)
    restore = actions.add_parser(
        "restore", help="return an archived plan or session", parents=[common]
    )
    restore_target = restore.add_mutually_exclusive_group(required=True)
    restore_target.add_argument("--plan", type=int, default=None, metavar="ID", help="plan id")
    restore_target.add_argument(
        "--session", type=int, default=None, metavar="ID", help="session id"
    )
    trim = actions.add_parser("trim", help="delete derived rows only", parents=[common])
    _days_flag(trim)
    _apply_flag(trim)
    vacuum = actions.add_parser("vacuum", help="reclaim free pages", parents=[common])
    _apply_flag(vacuum)
