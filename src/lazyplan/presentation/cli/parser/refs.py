"""Argument group for external reference commands."""

from __future__ import annotations

import argparse

from ....core.policies.refs import REF_KINDS


def add_ref_group(
    sub: argparse._SubParsersAction[argparse.ArgumentParser],
    common: argparse.ArgumentParser,
) -> None:
    """Add the top-level ref noun and its actions."""
    group = sub.add_parser(
        "ref",
        help="link, list, or unlink a plan's external references",
        parents=[common],
    )
    group.set_defaults(noun_group="ref", tree=False, plan=None, milestone=None)
    actions = group.add_subparsers(
        dest="action",
        required=True,
        metavar="ACTION",
        title="ref actions",
        help="what to do with external references",
    )
    link = actions.add_parser("link", help="link an external URL", parents=[common])
    link.add_argument("--plan", type=int, required=True, metavar="ID", help="plan id")
    link.add_argument("--url", required=True, metavar="URL", help="http(s) URL")
    link.add_argument("--provider", default="", metavar="NAME", help="provider (inferred)")
    link.add_argument("--type", choices=list(REF_KINDS), default="issue", help="reference kind")
    link.add_argument("--id", default="", metavar="EXTERNAL", help="external id")
    link.add_argument("--title", default="", metavar="TEXT", help="snapshot title")
    link.add_argument("--state", default="", metavar="TEXT", help="snapshot state")
    listing = actions.add_parser("list", help="list a plan's references", parents=[common])
    listing.add_argument("--plan", type=int, required=True, metavar="ID", help="plan id")
    unlink = actions.add_parser("unlink", help="remove a reference", parents=[common])
    unlink.add_argument("--plan", type=int, required=True, metavar="ID", help="plan id")
    unlink.add_argument("--id", type=int, default=0, metavar="ID", help="reference row id")
    unlink.add_argument("--url", default="", metavar="URL", help="reference URL")
