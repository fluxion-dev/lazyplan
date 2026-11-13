"""Argument group for session commands."""

from __future__ import annotations

import argparse

from lazyplan.core.policies.sessions import parse_session_id


def add_session_group(
    sub: argparse._SubParsersAction[argparse.ArgumentParser],
    common: argparse.ArgumentParser,
) -> None:
    """Add the top-level session noun and its actions."""
    group = sub.add_parser(
        "session",
        help="start, end, show, or list agent sessions",
        parents=[common],
    )
    group.set_defaults(noun_group="session", tree=False, plan=None, milestone=None)
    actions = group.add_subparsers(
        dest="action",
        required=True,
        metavar="ACTION",
        title="session actions",
        help="what to do with a session",
    )
    start = actions.add_parser("start", help="open a session", parents=[common])
    start.add_argument("--plan", type=int, default=None, metavar="ID", help="plan id")
    start.add_argument("--branch", default="", metavar="NAME", help="branch being worked")
    start.add_argument("--note", default="", metavar="TEXT", help="why this session started")
    start.add_argument("--force", action="store_true", help="end an existing open session first")
    start.add_argument(
        "--reason", default="", metavar="TEXT", help="why a worktree gate is being overridden"
    )
    end = actions.add_parser("end", help="close one session", parents=[common])
    end.add_argument(
        "--id", type=parse_session_id, default=None, metavar="ID", help="session id (S12 or 12)"
    )
    end.add_argument("--summary", default="", metavar="TEXT", help="what the session did")
    end.add_argument("--handoff", default="", metavar="TEXT", help="the next action")
    show = actions.add_parser("show", help="show one session and its events", parents=[common])
    show.add_argument(
        "--id",
        type=parse_session_id,
        default=None,
        metavar="ID",
        help="session id (default: active)",
    )
    show.add_argument(
        "--limit", type=int, default=50, metavar="N", help="events to include (default: 50)"
    )
    listing = actions.add_parser("list", help="list sessions", parents=[common])
    listing.add_argument("--plan", type=int, default=None, metavar="ID", help="plan id")
    listing.add_argument("--open", action="store_true", help="only sessions still open")
    listing.add_argument("--all", action="store_true", help="every actor, not just the current one")
    listing.add_argument(
        "--limit", type=int, default=20, metavar="N", help="rows to show (default: 20)"
    )
