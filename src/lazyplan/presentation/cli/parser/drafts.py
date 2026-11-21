"""Argument group for plan draft commands."""

from __future__ import annotations

import argparse

from ....core.kinds import (
    DRAFT_ANNOTATION_KINDS,
    DRAFT_ANNOTATION_STATUSES,
    DRAFT_STATUSES,
)


def add_draft_group(
    sub: argparse._SubParsersAction[argparse.ArgumentParser],
    common: argparse.ArgumentParser,
) -> None:
    """Add the top-level draft noun and its actions."""
    group = sub.add_parser(
        "draft",
        help="create, review, annotate, revise, or promote a plan draft",
        parents=[common],
    )
    group.set_defaults(noun_group="draft", tree=False, plan=None, milestone=None)
    actions = group.add_subparsers(
        dest="action",
        required=True,
        metavar="ACTION",
        title="draft actions",
        help="what to do with a plan draft",
    )
    listing = actions.add_parser("list", help="list plan drafts", parents=[common])
    listing.add_argument(
        "--status",
        choices=[*DRAFT_STATUSES, "all"],
        default="all",
        help="show only this state (default: all)",
    )
    show = actions.add_parser("show", help="show one draft document", parents=[common])
    show.add_argument("--id", type=int, required=True, metavar="ID", help="draft id")
    annotations = actions.add_parser(
        "annotations", help="list one draft's annotations", parents=[common]
    )
    annotations.add_argument("--id", type=int, required=True, metavar="ID", help="draft id")
    annotations.add_argument(
        "--status",
        choices=[*DRAFT_ANNOTATION_STATUSES, "all"],
        default="all",
        help="show only this annotation state (default: all)",
    )
    wait = actions.add_parser(
        "wait",
        help="block until a draft has open feedback (exit 0), is promoted (3), or times out (4)",
        parents=[common],
    )
    wait.add_argument("--id", type=int, required=True, metavar="ID", help="draft id")
    wait.add_argument(
        "--timeout",
        type=float,
        default=None,
        metavar="SECONDS",
        help="give up after this many seconds (default: wait forever)",
    )
    add = actions.add_parser(
        "add", help="store a validated plan document as a draft", parents=[common]
    )
    add.add_argument("--file", required=True, metavar="PATH", help="JSON plan document")
    sketch = actions.add_parser(
        "sketch", help="store a definition-only Markdown sketch as a draft", parents=[common]
    )
    sketch.add_argument("--file", required=True, metavar="PATH", help="Markdown sketch")
    formalize = actions.add_parser(
        "formalize",
        help="replace an approved sketch with its structured plan document",
        parents=[common],
    )
    formalize.add_argument("--id", type=int, required=True, metavar="ID", help="draft id")
    formalize.add_argument("--file", required=True, metavar="PATH", help="JSON plan document")
    formalize.add_argument(
        "--base-revision",
        type=int,
        required=True,
        metavar="N",
        help="the sketch revision this document formalizes",
    )
    formalize.add_argument(
        "--note", default="", metavar="TEXT", help="what this formalization adds"
    )
    revise = actions.add_parser(
        "revise", help="replace a draft document with a new revision", parents=[common]
    )
    revise.add_argument("--id", type=int, required=True, metavar="ID", help="draft id")
    revise.add_argument("--file", required=True, metavar="PATH", help="JSON plan document")
    revise.add_argument(
        "--base-revision",
        type=int,
        required=True,
        metavar="N",
        help="the revision this document replaces",
    )
    revise.add_argument("--note", default="", metavar="TEXT", help="what this revision changed")
    for verb, blurb in (
        ("ready", "return a clean revision to review"),
        ("promote", "create the plan from a clean draft"),
        ("delete", "delete a draft"),
    ):
        action = actions.add_parser(verb, help=blurb, parents=[common])
        action.add_argument("--id", type=int, required=True, metavar="ID", help="draft id")
    annotate = actions.add_parser(
        "annotate", help="annotate a draft block or quote", parents=[common]
    )
    annotate.add_argument("--id", type=int, required=True, metavar="ID", help="draft id")
    annotate.add_argument(
        "--block", required=True, metavar="KEY", help="block key, for example plan:why"
    )
    annotate.add_argument(
        "--kind",
        choices=list(DRAFT_ANNOTATION_KINDS),
        required=True,
        help="comment, question, or change",
    )
    annotate.add_argument("--text", required=True, metavar="TEXT", help="the annotation body")
    annotate.add_argument("--quote", default="", metavar="TEXT", help="exact selected text")
    annotate.add_argument("--start", type=int, default=0, metavar="N", help="selected start offset")
    annotate.add_argument("--end", type=int, default=0, metavar="N", help="selected end offset")
    respond = actions.add_parser(
        "respond", help="answer one annotation and mark it addressed", parents=[common]
    )
    respond.add_argument("--id", type=int, required=True, metavar="ID", help="annotation id")
    respond.add_argument("--response", required=True, metavar="TEXT", help="the answer")
    resolve = actions.add_parser("resolve", help="mark one annotation addressed", parents=[common])
    resolve.add_argument("--id", type=int, required=True, metavar="ID", help="annotation id")
    resolve.add_argument("--response", default="", metavar="TEXT", help="the answer")
    dismiss = actions.add_parser("dismiss", help="dismiss one annotation", parents=[common])
    dismiss.add_argument("--id", type=int, required=True, metavar="ID", help="annotation id")
    dismiss.add_argument("--reason", default="", metavar="TEXT", help="why it is dismissed")
