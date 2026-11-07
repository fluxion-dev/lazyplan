"""Legacy task aliases kept out of the main work parser."""

from __future__ import annotations

import argparse


def add_add_task(
    sub: argparse._SubParsersAction[argparse.ArgumentParser], common: argparse.ArgumentParser
) -> None:

    a = sub.add_parser(
        "add-task",
        help="legacy alias for `task add`",
        parents=[common],
    )
    a.add_argument(
        "--milestone",
        type=int,
        required=True,
        metavar="ID",
        help="id of the milestone that owns this task",
    )
    a.add_argument("--title", required=True, metavar="TEXT", help="title of the task (required)")
    a.add_argument(
        "--desc", default="", metavar="TEXT", help="what the task involves and what it needs"
    )
    a.add_argument(
        "--touch",
        action="append",
        default=[],
        metavar="PATH",
        help="repo-relative path or glob this task will edit (repeatable)",
    )
