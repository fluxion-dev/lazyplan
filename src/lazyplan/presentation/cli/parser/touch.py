"""Argument group for task touch-point commands."""

from __future__ import annotations

import argparse


def add_touch_group(
    sub: argparse._SubParsersAction[argparse.ArgumentParser],
    common: argparse.ArgumentParser,
) -> None:
    """Add the top-level touch noun and its actions."""
    group = sub.add_parser(
        "touch",
        help="add, list, or remove a task's expected file touch-points",
        parents=[common],
    )
    group.set_defaults(noun_group="touch", tree=False, plan=None, milestone=None)
    actions = group.add_subparsers(
        dest="action",
        required=True,
        metavar="ACTION",
        title="touch actions",
        help="what to do with touch-points",
    )
    add = actions.add_parser("add", help="add one or more paths", parents=[common])
    add.add_argument("--task", type=int, required=True, metavar="ID", help="task id")
    add.add_argument(
        "--path",
        action="append",
        required=True,
        metavar="PATH",
        help="repo-relative path or glob (repeatable)",
    )
    listing = actions.add_parser("list", help="list a task's paths", parents=[common])
    listing.add_argument("--task", type=int, required=True, metavar="ID", help="task id")
    remove = actions.add_parser("remove", help="remove one path", parents=[common])
    remove.add_argument("--task", type=int, required=True, metavar="ID", help="task id")
    remove.add_argument("--path", required=True, metavar="PATH", help="repo-relative path")
