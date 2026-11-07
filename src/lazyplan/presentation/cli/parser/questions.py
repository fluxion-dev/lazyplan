"""Argument groups for plan questions."""

from __future__ import annotations

import argparse

from ....core.kinds import QUESTION_STATUSES


def add_question_group(
    sub: argparse._SubParsersAction[argparse.ArgumentParser],
    common: argparse.ArgumentParser,
) -> None:
    """Add the top-level question noun and its actions."""
    group = sub.add_parser(
        "question",
        help="add, list, resolve, or reopen a plan question",
        parents=[common],
    )
    group.set_defaults(noun_group="question", tree=False, plan=None, milestone=None)
    actions = group.add_subparsers(
        dest="action",
        required=True,
        metavar="ACTION",
        title="question actions",
        help="what to do with a question",
    )
    add = actions.add_parser("add", help="add an open question", parents=[common])
    add.add_argument("--plan", type=int, required=True, metavar="ID", help="plan id")
    add.add_argument("--text", required=True, metavar="TEXT", help="the question")
    listing = actions.add_parser("list", help="list plan questions", parents=[common])
    listing.add_argument("--plan", type=int, required=True, metavar="ID", help="plan id")
    listing.add_argument(
        "--status",
        choices=[*QUESTION_STATUSES, "all"],
        default="open",
        help="show only this state (default: open)",
    )
    resolve = actions.add_parser("resolve", help="resolve one question", parents=[common])
    resolve.add_argument("--id", type=int, required=True, metavar="ID", help="question id")
    resolve.add_argument("--note", default="", metavar="TEXT", help="the answer or context")
    reopen = actions.add_parser("reopen", help="reopen one question", parents=[common])
    reopen.add_argument("--id", type=int, required=True, metavar="ID", help="question id")
    reopen.add_argument("--note", default="", metavar="TEXT", help="why it is open again")
