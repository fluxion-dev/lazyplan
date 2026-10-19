"""`lpui` argument parser (the agent/human CLI; the TUI is keyboard-only)."""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path

from .models import DEFAULT_TASK_PRIORITY, Status

_PARSER_DESCRIPTION = (
    "lazyplan: projects > stories > tasks in a per-repo SQLite DB "
    "(lpui; alias: lazyplan). Human TUI + agent-friendly CLI share one DB."
)

_PARSER_EPILOG = """\
database (first match wins):
  --db PATH | $LAZYPLAN_DB | ./.lazyplan/lazyplan.db (inside a repo) | ~/.local/share/lazyplan/lazyplan.db

examples:
  lpui                                   launch the TUI (same as `lpui ui`)
  lpui list                              ascii tree of projects > stories > tasks
  lpui list --status doing --priority p0
  lpui show --kind project --id 1        full context (why/what + criteria + children)
  lpui --actor alice add-project --title "API v2" --why ".." --what ".." --priority p1
  lpui --actor alice add-criteria --kind project --id 1 --text "Works offline"
  lpui --actor alice add-story --project 1 --title "Feature Y" --priority p1
  lpui --actor alice add-task --story 1 --title "Do X" --priority p0
  lpui status --kind task --id 3 --to done
  lpui link --kind task --id 3           attach HEAD commit (git repos only)
  lpui commits --kind task --id 3        list linked commits
  lpui feed --limit 20                   recent human/agent activity
  lpui export --format json > backup.json
  lpui import --file backup.json

vcs: link/unlink/commits need a git repo; outside git, link/unlink fail
  (exit 2) and commits reads empty. status --to done auto-captures HEAD.

flags work before or after the verb (`lpui list --json` == `lpui --json list`).
`--actor NAME` on writes surfaces who did what in `feed`.

workflow: interview the human for a project's why/what/acceptance criteria,
create it, then cut prioritized stories and tasks from the definition.

environment:
  LAZYPLAN_DB       sqlite path override (same as --db)

files:
  .lazyplan/lazyplan.db                      per-repo database (commit it to share)
  ~/.local/share/lazyplan/lazyplan.db    global fallback outside a repo

exit codes: 0 ok · 1 not found · 2 usage/error · 3 TUI unavailable (Textual missing).

more help:
  lpui <command> --help                  per-command flags and examples
  lpui help                              TUI keybindings (same as `?` in the TUI)
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
        help="sqlite path (default: $LAZYPLAN_DB, else ./.lazyplan/ in repo, else global)",
    )
    p.add_argument("--json", action="store_true", help="agent-friendly JSON output")
    p.add_argument("--version", action="store_true", help="print the installed version and exit")
    p.add_argument(
        "--actor",
        default=os.environ.get("USER", "human"),
        metavar="NAME",
        help="who is making this change (surfaced in feed; default: $USER or 'human')",
    )
    # repeat globals on every subcommand so `lpui list --json` works as well as
    # `lpui --json list`.
    # SUPPRESS defaults: an explicit global flag must survive when the
    # subcommand flag is absent (argparse would otherwise let the
    # subcommand default clobber it).
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--json", action="store_true", default=argparse.SUPPRESS, help="agent-friendly JSON output"
    )
    common.add_argument(
        "--version",
        action="store_true",
        default=argparse.SUPPRESS,
        help="print the installed version and exit",
    )
    common.add_argument(
        "--actor", default=argparse.SUPPRESS, metavar="NAME", help="who acted (shown in feed)"
    )
    sub = p.add_subparsers(dest="cmd", required=False, title="commands", metavar="COMMAND")

    init = sub.add_parser(
        "init", help="init .lazyplan/ in this repo (or global db)", parents=[common]
    )
    init.add_argument("--no-skills", action="store_true", help="skip the agent-skills wizard")
    init.add_argument("--yes", action="store_true", help="install default skills without prompting")
    init.add_argument(
        "--skills-scope",
        choices=["project", "global", "both", "none"],
        default="",
        metavar="SCOPE",
        help="install agent skills to a scope without prompting (none = skip)",
    )
    sub.add_parser("seed", help="insert demo project/stories/tasks", parents=[common])
    sub.add_parser("info", help="show resolved db path, repo root, counts", parents=[common])
    li = sub.add_parser("list", help="ascii tree of projects > stories > tasks", parents=[common])
    li.add_argument(
        "--status",
        choices=[v.value for v in Status] + ["all"],
        default=None,
        help="filter by status (default: all)",
    )
    li.add_argument(
        "--archived",
        action="store_true",
        help="show only archived projects (done over a day ago)",
    )
    li.add_argument("--project", type=int, default=None, metavar="ID", help="only this project")
    li.add_argument(
        "--priority",
        choices=["p0", "p1", "p2", "p3"],
        default=None,
        help="only this priority (p0 highest)",
    )

    a = sub.add_parser("add-project", help="agent/human: add a project", parents=[common])
    a.add_argument("--title", default=None, metavar="TEXT", help="project title")
    a.add_argument("--name", default=None, metavar="NAME", help="alias of --title")
    a.add_argument("--what", default="", metavar="TEXT", help="what gets built")
    a.add_argument("--desc", default=None, metavar="TEXT", help="alias of --what")
    a.add_argument("--why", default="", metavar="TEXT", help="why this exists")
    a.add_argument("--goal", default=None, metavar="TEXT", help="alias of --why")
    a.add_argument(
        "--priority", choices=["p0", "p1", "p2", "p3"], default="", help="priority (p0 highest)"
    )

    a = sub.add_parser("add-story", help="agent/human: add a story", parents=[common])
    a.add_argument("--project", type=int, required=True, metavar="ID", help="parent project id")
    a.add_argument("--title", required=True, metavar="TEXT", help="story title (required)")
    a.add_argument("--desc", default="", metavar="TEXT", help="details")
    a.add_argument(
        "--priority", choices=["p0", "p1", "p2", "p3"], default="", help="priority (p0 highest)"
    )

    a = sub.add_parser("add-task", help="agent/human: add a task", parents=[common])
    a.add_argument("--story", type=int, required=True, metavar="ID", help="parent story id")
    a.add_argument("--title", required=True, metavar="TEXT", help="task title (required)")
    a.add_argument("--desc", default="", metavar="TEXT", help="details / context")
    a.add_argument(
        "--priority",
        choices=["p0", "p1", "p2", "p3"],
        default=DEFAULT_TASK_PRIORITY,
        help="priority (default: p1; p0 highest)",
    )

    u = sub.add_parser(
        "update",
        help="edit title/details/why/priority",
        parents=[common],
    )
    u.add_argument(
        "--kind", choices=["project", "story", "task"], required=True, help="what to edit"
    )
    u.add_argument("--id", type=int, required=True, metavar="ID", help="row id")
    u.add_argument("--title", default=None, metavar="TEXT", help="new title")
    u.add_argument("--name", default=None, metavar="NAME", help="alias of --title for projects")
    u.add_argument("--desc", default=None, metavar="TEXT", help="new details")
    u.add_argument("--what", default=None, metavar="TEXT", help="alias of --desc for projects")
    u.add_argument("--why", default=None, metavar="TEXT", help="new why (projects)")
    u.add_argument("--goal", default=None, metavar="TEXT", help="alias of --why")
    u.add_argument(
        "--priority",
        choices=["p0", "p1", "p2", "p3", "none"],
        default=None,
        help="new priority (`none` clears)",
    )

    sh = sub.add_parser(
        "show", help="full context record: fields + criteria + children", parents=[common]
    )
    sh.add_argument(
        "--kind", choices=["project", "story", "task"], required=True, help="what to show"
    )
    sh.add_argument("--id", type=int, required=True, metavar="ID", help="row id")

    ac = sub.add_parser("add-criteria", help="add an acceptance-checklist item", parents=[common])
    ac.add_argument(
        "--kind", choices=["project", "story", "task"], required=True, help="parent kind"
    )
    ac.add_argument("--id", type=int, required=True, metavar="ID", help="parent id")
    ac.add_argument("--text", required=True, metavar="TEXT", help="criterion text (required)")
    lc = sub.add_parser("criteria", help="list acceptance criteria", parents=[common])
    lc.add_argument(
        "--kind", choices=["project", "story", "task"], required=True, help="parent kind"
    )
    lc.add_argument("--id", type=int, required=True, metavar="ID", help="parent id")
    for _name, _help in (("check", "tick a criterion done"), ("uncheck", "reopen a criterion")):
        cc = sub.add_parser(_name, help=_help, parents=[common])
        cc.add_argument("--id", type=int, required=True, metavar="ID", help="criteria id")
    dc = sub.add_parser("delete-criteria", help="remove a criterion by its id", parents=[common])
    dc.add_argument("--id", type=int, required=True, metavar="ID", help="criteria id")

    lk = sub.add_parser(
        "link", help="attach a git commit to a project/story/task", parents=[common]
    )
    lk.add_argument(
        "--kind", choices=["project", "story", "task"], required=True, help="what to link"
    )
    lk.add_argument("--id", type=int, required=True, metavar="ID", help="row id")
    lk.add_argument(
        "--sha",
        default=None,
        metavar="SHA",
        help="commit hash (default: current HEAD)",
    )
    ul = sub.add_parser(
        "unlink", help="detach a git commit from a project/story/task", parents=[common]
    )
    ul.add_argument(
        "--kind", choices=["project", "story", "task"], required=True, help="what to unlink"
    )
    ul.add_argument("--id", type=int, required=True, metavar="ID", help="row id")
    ul.add_argument("--sha", required=True, metavar="SHA", help="commit hash (required)")
    cm = sub.add_parser(
        "commits", help="list commits linked to a project/story/task", parents=[common]
    )
    cm.add_argument(
        "--kind", choices=["project", "story", "task"], required=True, help="what to list"
    )
    cm.add_argument("--id", type=int, required=True, metavar="ID", help="row id")

    ex = sub.add_parser("export", help="full dump (agents: --format json)", parents=[common])
    ex.add_argument(
        "--format",
        choices=["json", "markdown"],
        default="json",
        help="output format (default: json)",
    )
    im = sub.add_parser("import", help="load an `lpui export --format json` dump", parents=[common])
    im.add_argument("--file", required=True, metavar="PATH", help="dump file (required)")

    s = sub.add_parser("status", help="move project/story/task to a status", parents=[common])
    s.add_argument(
        "--kind", choices=["project", "story", "task"], required=True, help="what to move"
    )
    s.add_argument("--id", type=int, required=True, metavar="ID", help="row id")
    s.add_argument(
        "--to", choices=[v.value for v in Status], required=True, help="new status (required)"
    )

    sub.add_parser("reconcile", help="recompute parent statuses from children", parents=[common])

    d = sub.add_parser("delete", help="delete a project/story/task", parents=[common])
    d.add_argument(
        "--kind", choices=["project", "story", "task"], required=True, help="what to delete"
    )
    d.add_argument("--id", type=int, required=True, metavar="ID", help="row id")

    f = sub.add_parser("feed", help="recent agent/human activity", parents=[common])
    f.add_argument(
        "--limit", type=int, default=20, metavar="N", help="how many events (default: 20)"
    )
    f.add_argument("--follow", action="store_true", help="tail new events")
    f.add_argument(
        "--interval",
        type=float,
        default=1.0,
        metavar="SECS",
        help="poll interval for --follow (default: 1.0)",
    )
    w = sub.add_parser("watch", help="alias of feed --follow", parents=[common])
    w.add_argument(
        "--limit", type=int, default=20, metavar="N", help="how many events (default: 20)"
    )

    c = sub.add_parser("completion", help="shell completions", parents=[common])
    c.add_argument("--shell", choices=["bash", "zsh"], required=True, help="shell (required)")

    sub.add_parser("help", help="print shared help text (same as TUI ?)", parents=[common])
    sub.add_parser(
        "ui", help="launch Textual TUI (default when no command is given)", parents=[common]
    )
    return p
