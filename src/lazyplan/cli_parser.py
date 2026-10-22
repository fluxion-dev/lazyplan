"""`lpui` argument parser (the agent/human CLI; the TUI is keyboard-only)."""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path

from .kinds import KINDS
from .models import Status

_PARSER_DESCRIPTION = (
    "lazyplan keeps your plans, milestones, and tasks in a small database next to "
    "your code (run it as lpui, or by its long name lazyplan). You get a "
    "keyboard-driven screen, and your coding agent gets a command line that "
    "reads the same database."
)

_PARSER_EPILOG = """\
your database (the first match wins):
  --db PATH | $LAZYPLAN_DB | nearest team ./.agents/lazyplan/lazyplan.db walking up
  | ~/.lazyplan/lazyplan.db shared home (%LOCALAPPDATA%/lazyplan on Windows)

examples:
  lpui init --team                     share this repo's plan with the team
  lpui                                   open the screen (same as `lpui ui`)
  lpui plan list                         show plans as summaries with progress
  lpui plan list --tree                  show the full plan/milestone/task tree
  lpui plan list --status doing
  lpui plan show --id 1                  show one row with its why, what, checklist, and children
  lpui --actor alice plan add --title "API v2" --why ".." --what ".."
  lpui --actor alice criterion add --kind plan --id 1 --text "Works offline"
  lpui --actor alice milestone add --plan 1 --title "Feature Y" --desc "value"
  lpui --actor alice task add --milestone 1 --title "Do X" --desc "approach"
  lpui task move --id 3 --to done
  lpui link --kind task --id 3           attach the current commit (needs a git repo)
  lpui commits --kind task --id 3        list the attached commits
  lpui link-repo --kind plan --id 1 --repo ~/checkouts/api
  lpui repos --kind task --id 3 --effective
  lpui list --repo ~/checkouts/api
  lpui feed --limit 20                   show recent activity by you and your agents
  lpui upgrade [--check]                 self-update pipx/venv installs (no repo needed)
  lpui export --format json > backup.json
  lpui import --file backup.json

vcs: link, unlink, and commits need a git repo. Outside a repo, link and
  unlink fail (exit 2) and commits shows nothing. Marking a row done with
  status --to done attaches the current commit for you.

repos: link-repo, unlink-repo, and repos work anywhere (no git needed).
  A task with no explicit links inherits its milestone's repos, and a
  milestone inherits its plan's. list --repo matches effective repos.

flags work before or after the command (`lpui list --json` means the same as
`lpui --json list`). On commands that change data, `--actor NAME` records who
did it, and you can see it in `feed`.

workflow: starting a plan? Ask the human what to build, why it matters,
  and how to tell it is done. Save that as the plan. Then break it into
  milestones, and each milestone into prioritized tasks.

environment:
  LAZYPLAN_DB       which database file to use (same as --db)

files: shared home by default (--team opts a repo into shared storage)
  ~/.lazyplan/lazyplan.db                 your plans, every agent and folder (default)
  ~/.lazyplan/templates/                  creation templates shared by every agent
  .agents/lazyplan/lazyplan.db            team database for this repo (commit it to share)
  .agents/lazyplan/templates/{plan,milestone,task}.md  creation templates (commit them to share)

exit codes: 0 it worked · 1 id not found · 2 flags or input were wrong · 3 screen cannot start (Textual is missing).

more help:
  lpui <command> --help                  flags and examples for one command
  lpui help                              the screen's key bindings (same as `?` in the app)
  man lpui                               full manual (installed with the package)
"""


def package_version() -> str:
    """Version of the running code: pyproject next to the source tree, else installed dist metadata."""
    try:
        text = (Path(__file__).resolve().parent.parent.parent / "pyproject.toml").read_text()
    except OSError:
        text = ""
    m = re.search(r'^version = "(.*)"$', text, re.M) if text else None
    if m:
        return m.group(1)
    try:
        from importlib.metadata import PackageNotFoundError, version

        return version("lazyplan-tui")
    except PackageNotFoundError:
        return "unknown"


def build_parser() -> argparse.ArgumentParser:
    """lpui argument parser; globals repeat on every subcommand."""
    p = argparse.ArgumentParser(
        description=_PARSER_DESCRIPTION,
        epilog=_PARSER_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--db",
        default=None,
        metavar="PATH",
        help="which database file to use (default: $LAZYPLAN_DB, else ./.agents/lazyplan/ in a repo, else the global one)",
    )
    p.add_argument(
        "--json", action="store_true", help="print output as JSON so scripts and agents can read it"
    )
    p.add_argument("--version", action="store_true", help="print the installed version and exit")
    p.add_argument(
        "--actor",
        default=os.environ.get("USER", "human"),
        metavar="NAME",
        help="who is making this change (you see it in feed; default: $USER or 'human')",
    )
    # repeat globals on every subcommand so `lpui list --json` works as well as
    # `lpui --json list`.
    # SUPPRESS defaults: an explicit global flag must survive when the
    # subcommand flag is absent (argparse would otherwise let the
    # subcommand default clobber it).
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--json",
        action="store_true",
        default=argparse.SUPPRESS,
        help="print output as JSON so scripts and agents can read it",
    )
    common.add_argument(
        "--version",
        action="store_true",
        default=argparse.SUPPRESS,
        help="print the installed version and exit",
    )
    common.add_argument(
        "--actor",
        default=argparse.SUPPRESS,
        metavar="NAME",
        help="who made this change (you see it in feed)",
    )
    sub = p.add_subparsers(dest="cmd", required=False, title="commands", metavar="COMMAND")

    init = sub.add_parser(
        "init",
        help="set up agent skills locally (shared home) or share this repo with --team",
        parents=[common],
    )
    init.add_argument(
        "--no-skills",
        action="store_true",
        help="skip the setup wizard that installs helper files for your coding agent",
    )
    init.add_argument(
        "--yes",
        action="store_true",
        help="install the default agent helper files without asking first",
    )
    init.add_argument(
        "--skills-scope",
        choices=["project", "global", "both", "none"],
        default="",
        metavar="SCOPE",
        help="install agent helper files to one place without asking first (none = skip)",
    )
    init.add_argument(
        "--skills-dir",
        default=None,
        metavar="PATH",
        help="put the skill in this folder instead of the detected ones",
    )
    init.add_argument(
        "--team",
        action="store_true",
        help="write repo-shared files (.agents/lazyplan/, AGENTS.md pointer, templates) for teams",
    )
    init.add_argument(
        "--agents",
        default="",
        metavar="LIST",
        help="which agents to install for (space/comma list, 'all', or detected by default)",
    )
    sub.add_parser(
        "seed", help="add demo data: one plan with milestones and tasks", parents=[common]
    )
    sub.add_parser(
        "info",
        help="show which database file is in use, the repo root, and how many plans, milestones, and tasks you have",
        parents=[common],
    )
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

    # -- noun-first groups (canonical); legacy verbs below stay aliases ------
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
    _a = _actions.add_parser("list", help="list one milestone's tasks as a tree", parents=[common])
    _a.add_argument("--milestone", type=int, required=True, metavar="ID", help="milestone id")
    _plan_list_flags(_a)
    _a = _actions.add_parser("move", help="move a task to a status", parents=[common])
    _a.add_argument("--id", type=int, required=True, metavar="ID", help="task id")
    _a.add_argument("--to", choices=[v.value for v in Status], required=True, help="new status")
    _a = _actions.add_parser("delete", help="delete a task", parents=[common])
    _a.add_argument("--id", type=int, required=True, metavar="ID", help="task id")

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

    a = sub.add_parser("add-plan", help="legacy alias for `plan add`", parents=[common])
    a.add_argument("--title", default=None, metavar="TEXT", help="title of the plan")
    a.add_argument("--name", default=None, metavar="NAME", help="same as --title")
    a.add_argument("--what", default="", metavar="TEXT", help="what you will build")
    a.add_argument("--desc", default=None, metavar="TEXT", help="same as --what")
    a.add_argument("--why", default="", metavar="TEXT", help="why this plan exists")
    a.add_argument("--goal", default=None, metavar="TEXT", help="same as --why")

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
    lc = sub.add_parser("criteria", help="legacy alias for `criterion list`", parents=[common])
    lc.add_argument(
        "--kind",
        choices=list(KINDS),
        required=True,
        help="which kind of row to list",
    )
    lc.add_argument("--id", type=int, required=True, metavar="ID", help="id of the row")
    for _name, _help in (
        ("check", "legacy alias for `criterion tick`"),
        ("uncheck", "legacy alias for `criterion untick`"),
    ):
        cc = sub.add_parser(_name, help=_help, parents=[common])
        cc.add_argument(
            "--id", type=int, required=True, metavar="ID", help="id of the checklist item"
        )
    dc = sub.add_parser(
        "delete-criteria", help="legacy alias for `criterion delete`", parents=[common]
    )
    dc.add_argument("--id", type=int, required=True, metavar="ID", help="id of the checklist item")

    lk = sub.add_parser("link", help="attach a git commit to a row", parents=[common])
    lk.add_argument(
        "--kind",
        choices=list(KINDS),
        required=True,
        help="which kind of row to attach to",
    )
    lk.add_argument("--id", type=int, required=True, metavar="ID", help="id of the row")
    lk.add_argument(
        "--sha",
        default=None,
        metavar="SHA",
        help="which commit to attach (default: the current HEAD commit)",
    )
    ul = sub.add_parser("unlink", help="detach a git commit from a row", parents=[common])
    ul.add_argument(
        "--kind",
        choices=list(KINDS),
        required=True,
        help="which kind of row to detach from",
    )
    ul.add_argument("--id", type=int, required=True, metavar="ID", help="id of the row")
    ul.add_argument("--sha", required=True, metavar="SHA", help="which commit to detach (required)")
    cm = sub.add_parser("commits", help="list the commits attached to a row", parents=[common])
    cm.add_argument(
        "--kind",
        choices=list(KINDS),
        required=True,
        help="which kind of row to list",
    )
    cm.add_argument("--id", type=int, required=True, metavar="ID", help="id of the row")

    lr = sub.add_parser("link-repo", help="attach a repo checkout to a row", parents=[common])
    lr.add_argument(
        "--kind",
        choices=list(KINDS),
        required=True,
        help="which kind of row to attach to",
    )
    lr.add_argument("--id", type=int, required=True, metavar="ID", help="id of the row")
    lr.add_argument(
        "--repo",
        required=True,
        metavar="PATH",
        help="repo checkout path (absolute or relative; stored absolute)",
    )
    lr.add_argument(
        "--remote",
        default=None,
        metavar="URL",
        help="remote URL (default: git remote get-url origin for the path, else empty)",
    )
    ulr = sub.add_parser("unlink-repo", help="detach a repo checkout from a row", parents=[common])
    ulr.add_argument(
        "--kind",
        choices=list(KINDS),
        required=True,
        help="which kind of row to detach from",
    )
    ulr.add_argument("--id", type=int, required=True, metavar="ID", help="id of the row")
    ulr.add_argument("--repo", required=True, metavar="PATH", help="which repo path to detach")
    ulr.add_argument(
        "--remote",
        default=None,
        metavar="URL",
        help="only detach this remote (default: all remotes for the path)",
    )
    rp = sub.add_parser("repos", help="list the repos attached to a row", parents=[common])
    rp.add_argument(
        "--kind",
        choices=list(KINDS),
        required=True,
        help="which kind of row to list",
    )
    rp.add_argument("--id", type=int, required=True, metavar="ID", help="id of the row")
    rp.add_argument(
        "--effective",
        action="store_true",
        help="show inherited repos when the row has no explicit links",
    )

    ex = sub.add_parser(
        "export", help="save everything (agents: use --format json)", parents=[common]
    )
    ex.add_argument(
        "--format",
        choices=["json", "markdown"],
        default="json",
        help="which format to save in (default: json)",
    )
    ex.add_argument(
        "--plan",
        type=int,
        default=None,
        metavar="ID",
        help="export one plan only (default: whole db)",
    )
    ex.add_argument(
        "--file",
        default=None,
        metavar="PATH",
        help="write to a file instead of stdout",
    )
    im = sub.add_parser(
        "import", help="load a file saved by `lpui export --format json`", parents=[common]
    )
    im.add_argument(
        "--file", required=True, metavar="PATH", help="the saved file to load (required)"
    )

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

    sub.add_parser(
        "reconcile", help="fix up parent statuses to match their children", parents=[common]
    )

    d = sub.add_parser("delete", help="legacy alias for `<noun> delete`", parents=[common])
    d.add_argument(
        "--kind",
        choices=list(KINDS),
        required=True,
        help="which kind of row to delete",
    )
    d.add_argument("--id", type=int, required=True, metavar="ID", help="id of the row")

    f = sub.add_parser("feed", help="recent activity by you and your agents", parents=[common])
    f.add_argument(
        "--limit",
        type=int,
        default=20,
        metavar="N",
        help="how many recent events to show (default: 20)",
    )
    f.add_argument("--follow", action="store_true", help="keep showing new events as they arrive")
    f.add_argument(
        "--interval",
        type=float,
        default=1.0,
        metavar="SECS",
        help="how often to check for new events, in seconds (default: 1.0)",
    )
    w = sub.add_parser("watch", help="same as feed --follow", parents=[common])
    w.add_argument(
        "--limit",
        type=int,
        default=20,
        metavar="N",
        help="how many recent events to show (default: 20)",
    )

    c = sub.add_parser("completion", help="print tab-completions for your shell", parents=[common])
    c.add_argument(
        "--shell", choices=["bash", "zsh"], required=True, help="which shell you use (required)"
    )

    up = sub.add_parser(
        "upgrade",
        help="upgrade lpui itself to the latest release (pipx/venv installs)",
        parents=[common],
    )
    up.add_argument(
        "--check",
        action="store_true",
        help="only report the installed and latest versions, change nothing",
    )

    sub.add_parser(
        "help", help="show the screen's key bindings (same as ? in the app)", parents=[common]
    )
    sub.add_parser(
        "ui",
        help="open the keyboard-driven screen (this runs when you give no command)",
        parents=[common],
    )
    return p
