"""Argument groups for the agent registry and the hidden session alias."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from typing import Any

from lazyplan.core.policies.agents import STATUSES, parse_agent_id, parse_pid


def _any_id(text: str) -> int:
    """Parse A12, S12, a12, or 12 for the compatibility alias."""
    raw = str(text).strip()
    if raw[:1].lower() in ("a", "s"):
        raw = raw[1:]
    if not raw.isdigit() or int(raw) <= 0:
        raise argparse.ArgumentTypeError(f"invalid id {text!r}; use A12, S12, or 12")
    return int(raw)


def _show_ref(text: str) -> str:
    """Parse an agent or history id for show: A12, S12, or 12."""
    raw = str(text).strip()
    digits = raw[1:] if raw[:1].lower() in ("a", "s") else raw
    if not digits.isdigit() or int(digits) <= 0:
        raise argparse.ArgumentTypeError(f"invalid id {text!r}; use A12, S12, or 12")
    return raw


def _start_arguments(parser: argparse.ArgumentParser) -> None:
    """Identity and binding flags shared by start and its hidden alias."""
    parser.add_argument("--plan", type=int, default=None, metavar="ID", help="plan id")
    parser.add_argument("--task", type=int, default=None, metavar="ID", help="task id")
    parser.add_argument("--host", default="", metavar="NAME", help="host name")
    parser.add_argument("--session", default="", metavar="ID", help="host session id")
    parser.add_argument("--agent", default="", metavar="NAME", help="agent name")
    parser.add_argument("--role", default="primary", metavar="ROLE", help="primary or subagent")
    parser.add_argument("--model", default="", metavar="NAME", help="model name")
    parser.add_argument("--pid", type=parse_pid, default=0, metavar="PID", help="host process id")
    parser.add_argument("--note", default="", metavar="TEXT", help="why this agent started")
    parser.add_argument("--force", action="store_true", help="override a failed plan gate")
    parser.add_argument(
        "--reason", default="", metavar="TEXT", help="why a worktree gate is overridden"
    )


def _list_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--plan", type=int, default=None, metavar="ID", help="plan id")
    parser.add_argument("--open", action="store_true", help="only rows not ended")
    parser.add_argument("--live", action="store_true", help="only rows still running")
    parser.add_argument("--host", default="", metavar="NAME", help="only this host")
    parser.add_argument("--status", default="", choices=("", *STATUSES), help="only this status")
    parser.add_argument("--limit", type=int, default=20, metavar="N", help="rows (default: 20)")


def _show_arguments(parser: argparse.ArgumentParser, parse_id: Callable[[str], Any]) -> None:
    parser.add_argument("--id", type=parse_id, default=None, metavar="ID", help="row id")
    parser.add_argument(
        "--limit", type=int, default=50, metavar="N", help="events to include (default: 50)"
    )


def add_agent_group(
    sub: argparse._SubParsersAction[argparse.ArgumentParser],
    common: argparse.ArgumentParser,
) -> None:
    """Add the top-level agent noun and the hidden session alias."""
    group = sub.add_parser(
        "agent",
        help="start, end, show, list, sweep, or archive exact host agents",
        parents=[common],
    )
    group.set_defaults(noun_group="agent", tree=False, plan=None, milestone=None)
    actions = group.add_subparsers(
        dest="action",
        required=True,
        metavar="ACTION",
        title="agent actions",
        help="what to do with an agent",
    )

    start = actions.add_parser("start", help="register a managed agent", parents=[common])
    _start_arguments(start)
    end = actions.add_parser("end", help="end one agent and its live children", parents=[common])
    end.add_argument("--id", type=parse_agent_id, default=None, metavar="ID", help="agent id")
    end.add_argument("--summary", default="", metavar="TEXT", help="what the agent did")
    end.add_argument("--handoff", default="", metavar="TEXT", help="the next action")
    show = actions.add_parser("show", help="show one agent and its transitions", parents=[common])
    _show_arguments(show, _show_ref)
    listing = actions.add_parser("list", help="list registered agents", parents=[common])
    _list_arguments(listing)
    actions.add_parser("sweep", help="mark agents whose process is gone as lost", parents=[common])
    archive = actions.add_parser("archive", help="archive ended agents", parents=[common])
    archive.add_argument("--id", type=int, nargs="+", required=True, metavar="ID")
    restore = actions.add_parser("restore", help="restore one archived agent", parents=[common])
    restore.add_argument("--id", type=int, required=True, metavar="ID")
    history = actions.add_parser(
        "history", help="list read-only legacy session rows", parents=[common]
    )
    history.add_argument("--plan", type=int, default=None, metavar="ID", help="plan id")
    history.add_argument("--limit", type=int, default=20, metavar="N", help="rows (default: 20)")

    alias = sub.add_parser(
        "session",
        help=argparse.SUPPRESS,
        parents=[common],
    )
    alias.set_defaults(noun_group="session", tree=False, plan=None, milestone=None)
    alias_actions = alias.add_subparsers(
        dest="action",
        required=True,
        metavar="ACTION",
        help=argparse.SUPPRESS,
    )
    alias_start = alias_actions.add_parser("start", parents=[common])
    _start_arguments(alias_start)
    alias_end = alias_actions.add_parser("end", parents=[common])
    alias_end.add_argument("--id", type=_any_id, default=None, metavar="ID")
    alias_end.add_argument("--summary", default="", metavar="TEXT")
    alias_end.add_argument("--handoff", default="", metavar="TEXT")
    alias_show = alias_actions.add_parser("show", parents=[common])
    _show_arguments(alias_show, _show_ref)
    alias_list = alias_actions.add_parser("list", parents=[common])
    _list_arguments(alias_list)
    alias_list.add_argument("--all", action="store_true", help="include every actor")
    alias_list.add_argument("--history", action="store_true", help="read legacy session rows")
    # Keep the alias out of `lpui --help` while its actions stay callable.
    sub._choices_actions = [action for action in sub._choices_actions if action.dest != "session"]
