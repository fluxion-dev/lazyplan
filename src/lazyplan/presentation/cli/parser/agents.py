"""Argument group for ACP agent commands."""

from __future__ import annotations

import argparse


def add_agent_group(
    sub: argparse._SubParsersAction[argparse.ArgumentParser],
    common: argparse.ArgumentParser,
) -> None:
    """Add the top-level agent noun and its actions."""
    group = sub.add_parser(
        "agent",
        help="list, add, or remove ACP agents",
        parents=[common],
    )
    group.set_defaults(noun_group="agent", tree=False, plan=None, milestone=None)
    actions = group.add_subparsers(
        dest="action",
        required=True,
        metavar="ACTION",
        title="agent actions",
        help="what to do with the agent catalog",
    )
    actions.add_parser("list", help="show configured agents", parents=[common])
    add = actions.add_parser("add", help="add one ACP agent command", parents=[common])
    add.add_argument("key", metavar="KEY", help="short name, such as opencode")
    add.add_argument("--title", default="", metavar="TEXT", help="display name")
    add.add_argument(
        "--command",
        required=True,
        dest="executable",
        metavar="COMMAND",
        help="executable to launch, such as opencode",
    )
    add.add_argument(
        "--arg",
        action="append",
        default=[],
        dest="args",
        metavar="ARG",
        help="one argument after the command; repeat for each argument",
    )
    add.add_argument(
        "--env",
        action="append",
        default=[],
        dest="env",
        metavar="NAME=VALUE",
        help="one environment variable; repeat for each variable",
    )
    add.add_argument("--default", action="store_true", help="make this the default agent")
    remove = actions.add_parser("remove", help="remove one agent", parents=[common])
    remove.add_argument("key", metavar="KEY", help="agent key to remove")
