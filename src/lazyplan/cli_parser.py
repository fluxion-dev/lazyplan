"""`lpui` argument parser (the agent/human CLI; the TUI is keyboard-only)."""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path

from .kinds import KINDS
from .models import Status

_PARSER_DESCRIPTION = (
    "lazyplan keeps your plans, milestones, and tasks in one SQLite database, "
    "shared in your home by default or inside a repo through `lpui setup` "
    "(run it as lpui, or by its long name lazyplan). The first run sets up the "
    "database and agent skills. You get a keyboard-driven screen, and your "
    "coding agent gets a command line that reads the same data."
)

_PARSER_EPILOG = """\
your database (the first match wins):
  --db PATH | $LAZYPLAN_DB | nearest team ./.agents/lazyplan/lazyplan.db walking up
  | ~/.lazyplan/lazyplan.db shared home (%LOCALAPPDATA%/lazyplan on Windows)

examples:
  lpui                                   first run sets up, then opens the screen
  lpui setup                            re-run setup: placement, agents, and drift review
  lpui doctor                           read-only report of the resolved layout and findings
  lpui                                   open the screen (same as `lpui ui`)
  lpui plan list                         show plans as summaries with progress
  lpui plan list --tree                  show the full plan/milestone/task tree
  lpui plan list --status doing
  lpui --porcelain plan list --tree      stable tab-separated rows for an active agent
  lpui --porcelain next                  claim the first eligible task
  lpui --porcelain claim --id 3 --ttl 30m
  lpui --porcelain note add --kind task --id 3 --text "Decision or handoff"
  lpui --porcelain task block --id 3 --reason "waiting on design"
  lpui --porcelain criterion relate --id 1 --task 3
  lpui --porcelain trace --plan 1        # criterion -> task -> commit/PR
  lpui --porcelain lint --plan 1         # plan-quality findings
  lpui stats --since 30.days             # WIP, cycle time, aging, stale work
  lpui mcp                               # typed MCP server on stdio
  lpui --actor helper mcp --read-only    # read-only MCP for reviews
  lpui --porcelain task add --milestone 1 --title "Do X" --desc "approach"
  lpui plan show --id 1                  show one row with its why, what, checklist, and children
  lpui --actor alice plan add --title "API v2" --why ".." --what ".."
  lpui --actor alice criterion add --kind plan --id 1 --text "Works offline"
  lpui --actor alice milestone add --plan 1 --title "Feature Y" --desc "value"
  lpui --actor alice task add --milestone 1 --title "Do X" --desc "approach"
  lpui task move --id 3 --to done
  lpui task start --id 3                record an existing branch + base
  lpui task finish --id 3               link base..HEAD, done when clean
  lpui link --kind task --id 3           attach the current commit (needs a git repo)
  lpui commits --kind task --id 3        list the attached commits
  lpui git status --kind task --id 3     branch, dirty tree, and tracking per linked repo
  lpui git scan --since 7.days --dry-run link commits by Lazyplan: T3 trailers or branch name
  lpui pr auth                           show which GitHub token source is active
  lpui pr status --kind task --id 3      GitHub identity and auth for linked repos
  lpui pr refresh --kind task --id 3     resolve commits and branches to pull requests
  lpui link-repo --kind plan --id 1 --repo ~/checkouts/api
  lpui repos --kind task --id 3 --effective
  lpui list --repo ~/checkouts/api
  lpui feed --limit 20                   show recent activity by you and your agents
  lpui upgrade [--check]                 self-update pipx/venv installs (no repo needed)
  lpui export --format json > backup.json
  lpui import --file backup.json

vcs: link, unlink, git status, and git scan need a git repo. link accepts
  --repo to read a different checkout. commits reads cached links anywhere;
  --refresh re-resolves them and marks missing commits stale. Marking a row
  done links HEAD only when the tree is clean and HEAD is not already linked;
  task start records an existing branch and its base, and task finish links
  base..HEAD. lazyplan never writes to git.

repos: link-repo, unlink-repo, and repos work anywhere (no git needed).
  A task with no explicit links inherits its milestone's repos, and a
  milestone inherits its plan's. list --repo matches effective repos.

github: pr verbs read cached pull requests; only pr refresh calls GitHub.
  Auth order: LAZYPLAN_GITHUB_TOKEN, GITHUB_TOKEN, GH_TOKEN, then gh auth token.
  Tokens never enter the database or export. github.com only, read-only.

flags work before or after the command (`lpui list --json` means the same as
`lpui --json list`). On commands that change data, `--actor NAME` records who
did it, and you can see it in `feed`. `--porcelain` prints one tab-separated
row per record for active agents; `--json` wins when both are set.

workflow: starting a plan? Ask the human what to build, why it matters,
  and how to tell it is done. Save that as the plan. Then break it into
  milestones, and each milestone into prioritized tasks. Agents claim work
  with `next` (a lease, not an owner), renew or release it, note handoffs,
  and park blocked tasks with `task block --reason`. Relate each criterion to
  a proving task and run `lint` before check-off.

environment:
  LAZYPLAN_DB       which database file to use (same as --db)
  LAZYPLAN_PORCELAIN  print porcelain rows (1/true/yes/on)
  LAZYPLAN_NO_SETUP skip first-run setup and upgrade review
  LAZYPLAN_NO_SPINNER freeze the TUI doing spinner
  NO_COLOR          plain setup output (also CLICOLOR=0 and TERM=dumb)

files: shared home by default (`lpui setup --placement repo` opts a repo in)
  ~/.lazyplan/lazyplan.db                 your plans, every agent and folder (default)
  ~/.lazyplan/setup.json                  remembered setup choices and decisions
  ~/.lazyplan/templates/                  creation templates shared by every agent
  .agents/lazyplan/lazyplan.db            repo database when placement is repo
  .agents/lazyplan/templates/{plan,milestone,task}.md  repo creation templates

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
    p.add_argument(
        "--porcelain",
        action="store_true",
        help="print terse tab-separated rows for active agents (--json still wins)",
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
        "--porcelain",
        action="store_true",
        default=argparse.SUPPRESS,
        help="print terse tab-separated rows for active agents (--json still wins)",
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

    setup = sub.add_parser(
        "setup",
        help="re-run setup: where plans live, which agents get the skill, and layout review",
        parents=[common],
    )
    setup.add_argument(
        "--placement",
        choices=["home", "repo"],
        default="",
        help="store plans in your home or in this repo (repo needs a git checkout)",
    )
    setup.add_argument(
        "--agents",
        default="",
        metavar="LIST",
        help="which agents to install for (space/comma list, 'all', or 'none')",
    )
    setup.add_argument(
        "--skills-dir",
        default=None,
        metavar="PATH",
        help="put the skill in this folder instead of the detected ones",
    )
    setup.add_argument(
        "--no-skills",
        action="store_true",
        help="skip installing agent helper files",
    )
    setup.add_argument(
        "--hooks",
        dest="hooks",
        action="store_true",
        default=None,
        help="install lifecycle hooks for detected agents (the default)",
    )
    setup.add_argument(
        "--no-hooks",
        dest="hooks",
        action="store_false",
        help="remove installed lifecycle hooks and leave agent configs alone",
    )
    setup.add_argument(
        "--agents-pointer",
        dest="agents_pointer",
        action="store_true",
        default=None,
        help="add a marked lazyplan section to this repo's AGENTS.md",
    )
    setup.add_argument(
        "--no-agents-pointer",
        dest="agents_pointer",
        action="store_false",
        help="remove the marked lazyplan section from AGENTS.md",
    )
    setup.add_argument(
        "--yes",
        action="store_true",
        help="apply the current choices without asking",
    )
    setup.add_argument(
        "--post-upgrade",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    sub.add_parser(
        "seed", help="add demo data: one plan with milestones and tasks", parents=[common]
    )
    sub.add_parser(
        "info",
        help="show which database file is in use, the repo root, and how many plans, milestones, and tasks you have",
        parents=[common],
    )
    sub.add_parser(
        "doctor",
        help="read-only report of the resolved setup layout and findings",
        parents=[common],
    )
    au = sub.add_parser(
        "audit",
        help="measure commit linkage, status lag, and criteria gaps",
        parents=[common],
    )
    au.add_argument("--plan", type=int, default=None, metavar="ID", help="audit one plan")
    au.add_argument(
        "--since",
        default=None,
        metavar="DATE",
        help="window start, e.g. 7.days or 2026-10-01 (default: plan creation)",
    )
    au.add_argument(
        "--strict",
        action="store_true",
        help="exit 2 when coverage, lag, or criteria gaps breach the thresholds",
    )
    au.add_argument(
        "--min-coverage",
        type=float,
        default=0.8,
        metavar="RATIO",
        help="strict-mode minimum linked share (default: 0.8)",
    )
    au.add_argument(
        "--max-lag",
        type=float,
        default=1.0,
        metavar="N",
        help="strict-mode maximum median status lag in commits (default: 1)",
    )
    au.add_argument(
        "--max-gaps",
        type=int,
        default=0,
        metavar="N",
        help="strict-mode maximum open criteria on done rows (default: 0)",
    )
    au.add_argument(
        "--min-trace",
        type=float,
        default=0.0,
        metavar="RATIO",
        help="strict-mode minimum criteria with a proving task; 0 disables (default: 0)",
    )
    br = sub.add_parser(
        "brief",
        help="show the active plan, the next task, and unlinked commits",
        parents=[common],
    )
    br.add_argument("--plan", type=int, default=None, metavar="ID", help="brief one plan")
    nxt = sub.add_parser(
        "next",
        help="claim the next eligible task and move it doing",
        parents=[common],
    )
    nxt.add_argument("--plan", type=int, default=None, metavar="ID", help="only this plan")
    nxt.add_argument("--ttl", default="", metavar="TIME", help="lease length, e.g. 30m or 2.hours")
    nxt.add_argument("--note", default="", metavar="TEXT", help="note stored on the claim")
    nxt.add_argument(
        "--suggest", action="store_true", help="show the next task without claiming it"
    )
    cl = sub.add_parser(
        "claim",
        help="claim, renew, or release a task lease",
        parents=[common],
    )
    cl.add_argument(
        "action",
        nargs="?",
        choices=["take", "renew", "release"],
        default="take",
        help="take a new lease (default), renew it, or release it",
    )
    cl.add_argument("--id", type=int, required=True, metavar="ID", help="task id")
    cl.add_argument("--ttl", default="", metavar="TIME", help="lease length, e.g. 30m")
    cl.add_argument("--note", default="", metavar="TEXT", help="note stored on the claim")
    cl.add_argument(
        "--force", action="store_true", help="take over or release someone else's lease"
    )
    nt = sub.add_parser(
        "note",
        help="add or list append-only handoff notes",
        parents=[common],
    )
    nt.add_argument("action", choices=["add", "list"], help="add a note or list them")
    nt.add_argument(
        "--kind", choices=list(KINDS), required=True, help="which row the note belongs to"
    )
    nt.add_argument("--id", type=int, required=True, metavar="ID", help="row id")
    nt.add_argument("--text", default=None, metavar="TEXT", help="note text (add only)")
    nt.add_argument("--limit", type=int, default=None, metavar="N", help="latest N notes")
    cls = sub.add_parser(
        "claims",
        help="list active task leases with holder and expiry",
        parents=[common],
    )
    cls.add_argument("--plan", type=int, default=None, metavar="ID", help="only this plan")
    cls.add_argument("--all", action="store_true", help="include expired claims")
    who = sub.add_parser(
        "who",
        help="alias for `claims`: active task leases",
        parents=[common],
    )
    who.add_argument("--plan", type=int, default=None, metavar="ID", help="only this plan")
    who.add_argument("--all", action="store_true", help="include expired claims")
    st = sub.add_parser(
        "stats",
        help="show flow metrics: WIP, cycle time, throughput, aging, stale work",
        parents=[common],
    )
    st.add_argument(
        "--since",
        default="30.days",
        metavar="DATE",
        help="activity window, e.g. 30.days or 2026-01-01 (default: 30.days)",
    )
    st.add_argument(
        "--stale-after",
        default="1.days",
        metavar="TIME",
        help="todo age that counts as stale (default: 1.days)",
    )
    st.add_argument(
        "--by",
        dest="filter_actor",
        default=None,
        metavar="NAME",
        help="only completed/reopened activity by this actor",
    )
    li = sub.add_parser(
        "lint",
        help="lint a plan for traceability and task-quality gaps",
        parents=[common],
    )
    li.add_argument("--plan", type=int, required=True, metavar="ID", help="plan to lint")
    li.add_argument("--strict", action="store_true", help="exit 2 when any finding exists")
    mc = sub.add_parser(
        "mcp",
        help="serve the plan over MCP on stdio for agent hosts",
        parents=[common],
    )
    mc.add_argument(
        "--read-only",
        action="store_true",
        help="expose read tools only and never create the database",
    )
    tr = sub.add_parser(
        "trace",
        help="trace acceptance criteria to tasks, commits, and pull requests",
        parents=[common],
    )
    group = tr.add_mutually_exclusive_group(required=True)
    group.add_argument("--plan", type=int, metavar="ID", help="trace a whole plan's criteria")
    group.add_argument("--criterion", type=int, metavar="ID", help="trace one criterion")
    hk = sub.add_parser(
        "hook",
        help="read a host lifecycle event and print a reminder",
        parents=[common],
    )
    hk.add_argument(
        "event",
        choices=["session-start", "prompt-submit", "post-tool", "stop", "pre-compact"],
        help="which lifecycle event fired",
    )
    hk.add_argument(
        "--host",
        choices=["opencode", "claude", "gemini", "codex", "cursor"],
        default="",
        help="host emitting the event (inferred from the payload when omitted)",
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
    sh.add_argument("--files", action="store_true", help="list changed files per commit")

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
        "--repo",
        default=None,
        metavar="PATH",
        help="checkout to read the commit from (default: the current directory)",
    )
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
    cm.add_argument("--files", action="store_true", help="list changed files per commit")
    cm.add_argument(
        "--refresh",
        action="store_true",
        help="re-resolve cached commit metadata and mark missing commits stale",
    )

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
