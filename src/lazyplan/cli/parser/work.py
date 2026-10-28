"""Argument groups for work commands."""

from __future__ import annotations

import argparse

from ...kinds import KINDS
from ...models import Status


def add_list(
    sub: argparse._SubParsersAction[argparse.ArgumentParser], common: argparse.ArgumentParser
) -> None:

    li = sub.add_parser(
        "list", help="show plans as summaries (add --tree for the full tree)", parents=[common]
    )
    li.add_argument(
        "--status",
        choices=[v.value for v in Status] + ["all"],
        default=None,
        help="show only rows with this status (default: all)",
    )
    li.add_argument(
        "--archived",
        action="store_true",
        help="show only finished plans older than a day",
    )
    li.add_argument("--plan", type=int, default=None, metavar="ID", help="show only this plan")
    li.add_argument(
        "--all",
        action="store_true",
        help="show every plan instead of just recent ones",
    )
    li.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="show no more than N plans",
    )
    li.add_argument(
        "--repo",
        default=None,
        metavar="PATH",
        help="show only rows linked to this repo (matches effective repos)",
    )
    li.add_argument(
        "--tree",
        action="store_true",
        help="show the full plan/milestone/task tree instead of plan summaries",
    )
    li.add_argument(
        "--milestone",
        type=int,
        default=None,
        metavar="ID",
        help="show only this milestone and its tasks (implies --tree)",
    )


def add_show(
    sub: argparse._SubParsersAction[argparse.ArgumentParser], common: argparse.ArgumentParser
) -> None:

    sh = sub.add_parser(
        "show",
        help="legacy alias for `<noun> show`",
        parents=[common],
    )
    sh.add_argument(
        "--kind",
        choices=list(KINDS),
        required=True,
        help="which kind of row to show",
    )
    sh.add_argument("--id", type=int, required=True, metavar="ID", help="id of the row")
    sh.add_argument("--files", action="store_true", help="list changed files per commit")


def add_status(
    sub: argparse._SubParsersAction[argparse.ArgumentParser], common: argparse.ArgumentParser
) -> None:

    s = sub.add_parser("status", help="legacy alias for `<noun> move`", parents=[common])
    s.add_argument(
        "--kind",
        choices=list(KINDS),
        required=True,
        help="which kind of row to move",
    )
    s.add_argument("--id", type=int, required=True, metavar="ID", help="id of the row")
    s.add_argument(
        "--to", choices=[v.value for v in Status], required=True, help="the new status (required)"
    )


def add_reconcile(
    sub: argparse._SubParsersAction[argparse.ArgumentParser], common: argparse.ArgumentParser
) -> None:

    sub.add_parser(
        "reconcile", help="fix up parent statuses to match their children", parents=[common]
    )


def add_delete(
    sub: argparse._SubParsersAction[argparse.ArgumentParser], common: argparse.ArgumentParser
) -> None:

    d = sub.add_parser("delete", help="legacy alias for `<noun> delete`", parents=[common])
    d.add_argument(
        "--kind",
        choices=list(KINDS),
        required=True,
        help="which kind of row to delete",
    )
    d.add_argument("--id", type=int, required=True, metavar="ID", help="id of the row")


def add_update(
    sub: argparse._SubParsersAction[argparse.ArgumentParser], common: argparse.ArgumentParser
) -> None:

    u = sub.add_parser(
        "update",
        help="legacy alias for `plan|milestone|task edit`",
        parents=[common],
    )
    u.add_argument(
        "--kind",
        choices=list(KINDS),
        required=True,
        help="which kind of row to change",
    )
    u.add_argument("--id", type=int, required=True, metavar="ID", help="id of the row")
    u.add_argument("--title", default=None, metavar="TEXT", help="the new title")
    u.add_argument("--name", default=None, metavar="NAME", help="same as --title, for plans")
    u.add_argument("--desc", default=None, metavar="TEXT", help="the new details")
    u.add_argument("--what", default=None, metavar="TEXT", help="same as --desc, for plans")
    u.add_argument("--why", default=None, metavar="TEXT", help="the new reason why (plans)")
    u.add_argument("--goal", default=None, metavar="TEXT", help="same as --why")


def add_add_plan(
    sub: argparse._SubParsersAction[argparse.ArgumentParser], common: argparse.ArgumentParser
) -> None:

    a = sub.add_parser("add-plan", help="legacy alias for `plan add`", parents=[common])
    a.add_argument("--title", default=None, metavar="TEXT", help="title of the plan")
    a.add_argument("--name", default=None, metavar="NAME", help="same as --title")
    a.add_argument("--what", default="", metavar="TEXT", help="what you will build")
    a.add_argument("--desc", default=None, metavar="TEXT", help="same as --what")
    a.add_argument("--why", default="", metavar="TEXT", help="why this plan exists")
    a.add_argument("--goal", default=None, metavar="TEXT", help="same as --why")


def add_add_milestone(
    sub: argparse._SubParsersAction[argparse.ArgumentParser], common: argparse.ArgumentParser
) -> None:

    a = sub.add_parser(
        "add-milestone",
        help="legacy alias for `milestone add`",
        parents=[common],
    )
    a.add_argument(
        "--plan",
        type=int,
        required=True,
        metavar="ID",
        help="id of the plan that owns this milestone",
    )
    a.add_argument(
        "--title", required=True, metavar="TEXT", help="title of the milestone (required)"
    )
    a.add_argument("--desc", default="", metavar="TEXT", help="extra details about the milestone")


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


def add_add_criteria(
    sub: argparse._SubParsersAction[argparse.ArgumentParser], common: argparse.ArgumentParser
) -> None:

    ac = sub.add_parser("add-criteria", help="legacy alias for `criterion add`", parents=[common])
    ac.add_argument(
        "--kind",
        choices=list(KINDS),
        required=True,
        help="which kind of row this item belongs to",
    )
    ac.add_argument(
        "--id", type=int, required=True, metavar="ID", help="id of the row this item belongs to"
    )
    ac.add_argument("--text", required=True, metavar="TEXT", help="the checklist text (required)")


def add_criteria(
    sub: argparse._SubParsersAction[argparse.ArgumentParser], common: argparse.ArgumentParser
) -> None:

    lc = sub.add_parser("criteria", help="legacy alias for `criterion list`", parents=[common])
    lc.add_argument(
        "--kind",
        choices=list(KINDS),
        required=True,
        help="which kind of row to list",
    )
    lc.add_argument("--id", type=int, required=True, metavar="ID", help="id of the row")


def add_delete_criteria(
    sub: argparse._SubParsersAction[argparse.ArgumentParser], common: argparse.ArgumentParser
) -> None:

    dc = sub.add_parser(
        "delete-criteria", help="legacy alias for `criterion delete`", parents=[common]
    )
    dc.add_argument("--id", type=int, required=True, metavar="ID", help="id of the checklist item")


def add_noun_groups(
    sub: argparse._SubParsersAction[argparse.ArgumentParser], common: argparse.ArgumentParser
) -> None:

    def _noun_group(
        noun: str, blurb: str
    ) -> tuple[argparse.ArgumentParser, argparse._SubParsersAction]:
        group = sub.add_parser(noun, help=blurb, parents=[common])
        group.set_defaults(noun_group=noun, tree=False, plan=None, milestone=None)
        actions = group.add_subparsers(
            dest="action",
            required=True,
            metavar="ACTION",
            title=f"{noun} actions",
            help=f"what to do with a {noun}",
        )
        return group, actions

    def _title_flags(parser: argparse.ArgumentParser, required: bool = False) -> None:
        parser.add_argument("--title", required=required, metavar="TEXT", help="the title")
        parser.add_argument("--name", default=None, metavar="NAME", help="same as --title")

    def _plan_list_flags(parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--status",
            choices=[v.value for v in Status] + ["all"],
            default=None,
            help="show only rows with this status",
        )
        parser.add_argument("--archived", action="store_true", help="show only finished plans")
        parser.add_argument("--all", action="store_true", help="show every plan")
        parser.add_argument(
            "--limit", type=int, default=None, metavar="N", help="cap the plan count"
        )
        parser.add_argument("--repo", default=None, metavar="PATH", help="filter by linked repo")
        parser.add_argument("--tree", action="store_true", help="show the full tree")

    _group, _actions = _noun_group("plan", "add, edit, show, list, move, or delete a plan")
    _a = _actions.add_parser("add", help="add a plan", parents=[common])
    _title_flags(_a)
    _a.add_argument("--what", default="", metavar="TEXT", help="what you will build")
    _a.add_argument("--desc", default=None, metavar="TEXT", help="same as --what")
    _a.add_argument("--why", default="", metavar="TEXT", help="why this plan exists")
    _a.add_argument("--goal", default=None, metavar="TEXT", help="same as --why")
    _a = _actions.add_parser("edit", help="change a plan", parents=[common])
    _a.add_argument("--id", type=int, required=True, metavar="ID", help="plan id")
    _title_flags(_a)
    _a.add_argument("--what", default=None, metavar="TEXT", help="the new what")
    _a.add_argument("--desc", default=None, metavar="TEXT", help="same as --what")
    _a.add_argument("--why", default=None, metavar="TEXT", help="the new why")
    _a.add_argument("--goal", default=None, metavar="TEXT", help="same as --why")
    _a = _actions.add_parser("show", help="show one plan", parents=[common])
    _a.add_argument("--id", type=int, required=True, metavar="ID", help="plan id")
    _a.add_argument("--files", action="store_true", help="list changed files per commit")
    _a = _actions.add_parser("list", help="list plans as summaries", parents=[common])
    _plan_list_flags(_a)
    _a = _actions.add_parser("move", help="move a plan to a status", parents=[common])
    _a.add_argument("--id", type=int, required=True, metavar="ID", help="plan id")
    _a.add_argument("--to", choices=[v.value for v in Status], required=True, help="new status")
    _a = _actions.add_parser("delete", help="delete a plan", parents=[common])
    _a.add_argument("--id", type=int, required=True, metavar="ID", help="plan id")

    _group, _actions = _noun_group(
        "milestone", "add, edit, show, list, move, or delete a milestone"
    )
    _a = _actions.add_parser("add", help="add a milestone", parents=[common])
    _a.add_argument("--plan", type=int, required=True, metavar="ID", help="owning plan id")
    _title_flags(_a, required=True)
    _a.add_argument("--desc", default="", metavar="TEXT", help="details")
    _a = _actions.add_parser("edit", help="change a milestone", parents=[common])
    _a.add_argument("--id", type=int, required=True, metavar="ID", help="milestone id")
    _title_flags(_a)
    _a.add_argument("--desc", default=None, metavar="TEXT", help="the new details")
    _a = _actions.add_parser("show", help="show one milestone", parents=[common])
    _a.add_argument("--id", type=int, required=True, metavar="ID", help="milestone id")
    _a.add_argument("--files", action="store_true", help="list changed files per commit")
    _a = _actions.add_parser("list", help="list one plan's milestones as a tree", parents=[common])
    _a.add_argument("--plan", type=int, required=True, metavar="ID", help="plan id")
    _plan_list_flags(_a)
    _a = _actions.add_parser("move", help="move a milestone to a status", parents=[common])
    _a.add_argument("--id", type=int, required=True, metavar="ID", help="milestone id")
    _a.add_argument("--to", choices=[v.value for v in Status], required=True, help="new status")
    _a = _actions.add_parser("delete", help="delete a milestone", parents=[common])
    _a.add_argument("--id", type=int, required=True, metavar="ID", help="milestone id")

    _group, _actions = _noun_group("task", "add, edit, show, list, move, or delete a task")
    _a = _actions.add_parser("add", help="add a task", parents=[common])
    _a.add_argument(
        "--milestone", type=int, required=True, metavar="ID", help="owning milestone id"
    )
    _title_flags(_a, required=True)
    _a.add_argument("--desc", default="", metavar="TEXT", help="details")
    _a = _actions.add_parser("edit", help="change a task", parents=[common])
    _a.add_argument("--id", type=int, required=True, metavar="ID", help="task id")
    _title_flags(_a)
    _a.add_argument("--desc", default=None, metavar="TEXT", help="the new details")
    _a = _actions.add_parser("show", help="show one task", parents=[common])
    _a.add_argument("--id", type=int, required=True, metavar="ID", help="task id")
    _a.add_argument("--files", action="store_true", help="list changed files per commit")
    _a = _actions.add_parser("list", help="list one milestone's tasks as a tree", parents=[common])
    _a.add_argument("--milestone", type=int, required=True, metavar="ID", help="milestone id")
    _plan_list_flags(_a)
    _a = _actions.add_parser("move", help="move a task to a status", parents=[common])
    _a.add_argument("--id", type=int, required=True, metavar="ID", help="task id")
    _a.add_argument("--to", choices=[v.value for v in Status], required=True, help="new status")
    _a = _actions.add_parser("delete", help="delete a task", parents=[common])
    _a.add_argument("--id", type=int, required=True, metavar="ID", help="task id")
    _a = _actions.add_parser("block", help="block a task and record the reason", parents=[common])
    _a.add_argument("--id", type=int, required=True, metavar="ID", help="task id")
    _a.add_argument("--reason", required=True, metavar="TEXT", help="why the task is blocked")
    _a = _actions.add_parser("unblock", help="clear a task's blocked flag", parents=[common])
    _a.add_argument("--id", type=int, required=True, metavar="ID", help="task id")
    _a = _actions.add_parser("start", help="record an existing branch on a task", parents=[common])
    _a.add_argument("--id", type=int, required=True, metavar="ID", help="task id")
    _a.add_argument(
        "--repo",
        default=None,
        metavar="PATH",
        help="checkout to use (default: the task's linked repo, else cwd)",
    )
    _a.add_argument(
        "--branch",
        default=None,
        metavar="NAME",
        help="existing branch to record (default: the current branch)",
    )
    _a = _actions.add_parser(
        "finish", help="link branch commits and finish a task", parents=[common]
    )
    _a.add_argument("--id", type=int, required=True, metavar="ID", help="task id")
    _a.add_argument(
        "--repo",
        default=None,
        metavar="PATH",
        help="checkout to read (default: the task's recorded branch)",
    )
    _a.add_argument(
        "--require-pr",
        action="store_true",
        help="finish only when a pull request is linked",
    )
    _a.add_argument(
        "--require-checks",
        action="store_true",
        help="finish only when every linked PR's checks pass",
    )
    _a.add_argument(
        "--override",
        default="",
        metavar="REASON",
        help="record why a failed gate is being overridden",
    )

    _group, _actions = _noun_group("issue", "import provider issues into the journal")
    _a = _actions.add_parser("import", help="import GitHub or Linear issues", parents=[common])
    _a.add_argument("--provider", choices=["github", "linear"], required=True)
    _a.add_argument("--repo", default=None, metavar="OWNER/REPO", help="GitHub repository")
    _a.add_argument("--file", default=None, metavar="PATH", help="Linear JSON export")
    _a.add_argument(
        "--as",
        dest="as_kind",
        choices=["plan", "task"],
        default="plan",
        help="import as plan or task",
    )
    _a.add_argument("--milestone", type=int, default=0, metavar="ID", help="task placement")
    _a.add_argument("--dry-run", action="store_true", help="report without writing")
    _group, _actions = _noun_group(
        "criterion", "add, list, tick, untick, or delete an acceptance criterion"
    )
    _a = _actions.add_parser("add", help="add a criterion", parents=[common])
    _a.add_argument("--kind", choices=list(KINDS), required=True, help="parent kind")
    _a.add_argument("--id", type=int, required=True, metavar="ID", help="parent id")
    _a.add_argument("--text", required=True, metavar="TEXT", help="criterion text")
    _a = _actions.add_parser("list", help="list a row's criteria", parents=[common])
    _a.add_argument("--kind", choices=list(KINDS), required=True, help="parent kind")
    _a.add_argument("--id", type=int, required=True, metavar="ID", help="parent id")
    _a = _actions.add_parser("tick", help="tick one criterion", parents=[common])
    _a.add_argument("--id", type=int, required=True, metavar="ID", help="criterion id")
    _a = _actions.add_parser("untick", help="reopen one criterion", parents=[common])
    _a.add_argument("--id", type=int, required=True, metavar="ID", help="criterion id")
    _a = _actions.add_parser("delete", help="delete one criterion", parents=[common])
    _a.add_argument("--id", type=int, required=True, metavar="ID", help="criterion id")
    _a = _actions.add_parser(
        "relate", help="record that a task proves a criterion", parents=[common]
    )
    _a.add_argument("--id", type=int, required=True, metavar="ID", help="criterion id")
    _a.add_argument("--task", type=int, required=True, metavar="ID", help="proving task id")
    _a = _actions.add_parser(
        "unrelate", help="remove a criterion-task proof relation", parents=[common]
    )
    _a.add_argument("--id", type=int, required=True, metavar="ID", help="criterion id")
    _a.add_argument("--task", type=int, required=True, metavar="ID", help="proving task id")

    _group, _actions = _noun_group("git", "inspect the checkouts linked to a row (no network)")
    _a = _actions.add_parser(
        "status", help="branch, dirty tree, and tracking state", parents=[common]
    )
    _a.add_argument("--kind", choices=list(KINDS), default=None, help="row kind")
    _a.add_argument("--id", type=int, default=None, metavar="ID", help="row id")
    _a.add_argument(
        "--repo",
        default=None,
        metavar="PATH",
        help="inspect one checkout instead of the row's effective repos",
    )
    _a = _actions.add_parser(
        "scan", help="link commits by Lazyplan trailers or branch name", parents=[common]
    )
    _a.add_argument("--repo", default=None, metavar="PATH", help="checkout to scan (default: cwd)")
    _a.add_argument("--since", default="", metavar="DATE", help="git --since value, e.g. 7.days")
    _a.add_argument("--limit", type=int, default=50, metavar="N", help="scan at most N commits")
    _a.add_argument(
        "--dry-run",
        action="store_true",
        help="show matches without writing links",
    )
    _a.add_argument("--kind", choices=list(KINDS), default=None, help="limit to one row kind")
    _a.add_argument("--id", type=int, default=None, metavar="ID", help="limit to one row id")

    _group, _actions = _noun_group("pr", "read-only GitHub pull requests and auth")
    _a = _actions.add_parser(
        "auth", help="show which GitHub token source is active", parents=[common]
    )
    _a = _actions.add_parser(
        "status", help="GitHub identity and auth for linked repos", parents=[common]
    )
    _a.add_argument("--kind", choices=list(KINDS), default=None, help="row kind")
    _a.add_argument("--id", type=int, default=None, metavar="ID", help="row id")
    _a.add_argument(
        "--repo",
        default=None,
        metavar="PATH",
        help="inspect one checkout instead of the row's effective repos",
    )
    _a = _actions.add_parser("list", help="list linked pull requests", parents=[common])
    _a.add_argument("--kind", choices=list(KINDS), required=True, help="row kind")
    _a.add_argument("--id", type=int, required=True, metavar="ID", help="row id")
    _a = _actions.add_parser("show", help="show one linked pull request", parents=[common])
    _a.add_argument("--kind", choices=list(KINDS), required=True, help="row kind")
    _a.add_argument("--id", type=int, required=True, metavar="ID", help="row id")
    _a.add_argument("--number", type=int, required=True, metavar="N", help="pull request number")
    _a = _actions.add_parser("link", help="link a pull request URL to a row", parents=[common])
    _a.add_argument("--kind", choices=list(KINDS), required=True, help="row kind")
    _a.add_argument("--id", type=int, required=True, metavar="ID", help="row id")
    _a.add_argument("--url", required=True, metavar="URL", help="GitHub pull request URL")
    _a.add_argument("--title", default=None, metavar="TEXT", help="optional PR title")
    _a.add_argument("--state", default=None, metavar="STATE", help="optional PR state")
    _a = _actions.add_parser("unlink", help="detach one pull request", parents=[common])
    _a.add_argument("--kind", choices=list(KINDS), required=True, help="row kind")
    _a.add_argument("--id", type=int, required=True, metavar="ID", help="row id")
    _a.add_argument("--number", type=int, required=True, metavar="N", help="pull request number")
    _a = _actions.add_parser("refresh", help="resolve commits to PRs", parents=[common])
    _a.add_argument("--kind", choices=list(KINDS), required=True, help="row kind")
    _a.add_argument("--id", type=int, required=True, metavar="ID", help="row id")


def add_criterion_groups(
    sub: argparse._SubParsersAction[argparse.ArgumentParser], common: argparse.ArgumentParser
) -> None:

    for _name, _help in (
        ("check", "legacy alias for `criterion tick`"),
        ("uncheck", "legacy alias for `criterion untick`"),
    ):
        cc = sub.add_parser(_name, help=_help, parents=[common])
        cc.add_argument(
            "--id", type=int, required=True, metavar="ID", help="id of the checklist item"
        )
