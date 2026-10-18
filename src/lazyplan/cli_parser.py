"""`lpui` argument parser (every verb the CLI and TUI command bar share)."""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path

from .models import Status

_PARSER_DESCRIPTION = (
    "lazyplan: projects > stories > tasks in a per-repo SQLite DB "
    "(lpui; alias: lazyplan). Human TUI + agent-friendly CLI share one DB."
)

_PARSER_EPILOG = """\
database (first match wins):
  --db PATH | $LAZYPLAN_DB | ./.plan/lazyplan.db (inside a repo) | ~/.local/share/lazyplan/lazyplan.db

examples:
  lpui                                   launch the TUI (same as `lpui ui`)
  lpui list                              ascii tree of projects > stories > tasks
  lpui list --status doing --owner alice --priority p0
  lpui gantt --tasks --width 60          ascii roadmap (`*` critical, `!` blocked)
  lpui show --kind story --id 1          full context (fields + links + children)
  lpui --actor alice add-task --story 1 --title "Fix bug" --priority p1
  lpui status --kind task --id 3 --to done
  lpui propose --kind task --parent 1 --title "Refactor X"
  lpui proposals                         human approves with `4` then `a` in the TUI
  lpui ask --question "Which scope?"     lpui questions / lpui answer --id 1 --text ..
  lpui feed --limit 20                   recent human/agent activity
  lpui export --format json > backup.json
  lpui import --file backup.json

flags work before or after the verb (`lpui list --json` == `lpui --json list`).
`--actor NAME` on writes surfaces who did what in `feed`.

environment:
  LAZYPLAN_DB       sqlite path override (same as --db)
  LAZYPLAN_PG_DSN   postgres DSN for `sync` (or pass --dsn)

files:
  .plan/lazyplan.db                      per-repo database (commit it to share)
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
        help="sqlite path (default: $LAZYPLAN_DB, else ./.plan/ in repo, else global)",
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

    init = sub.add_parser("init", help="init .plan/ in this repo (or global db)", parents=[common])
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
        "--status", choices=[v.value for v in Status], default=None, help="filter by status"
    )
    li.add_argument("--project", type=int, default=None, metavar="ID", help="only this project")
    li.add_argument("--owner", default=None, metavar="NAME", help="only rows owned by NAME")
    li.add_argument(
        "--priority",
        choices=["p0", "p1", "p2", "p3"],
        default=None,
        help="only this priority (p0 highest)",
    )
    g = sub.add_parser("gantt", help="ascii gantt of stories (+tasks)", parents=[common])
    g.add_argument("--width", type=int, default=40, metavar="N", help="bar width (default: 40)")
    g.add_argument(
        "--status", choices=[v.value for v in Status], default=None, help="filter by status"
    )
    g.add_argument("--project", type=int, default=None, metavar="ID", help="only this project")
    g.add_argument("--owner", default=None, metavar="NAME", help="only rows owned by NAME")
    g.add_argument(
        "--priority",
        choices=["p0", "p1", "p2", "p3"],
        default=None,
        help="only this priority (p0 highest)",
    )
    g.add_argument("--tasks", action="store_true", help="also render task bars (default: stories)")

    a = sub.add_parser("add-project", help="agent/human: add a project", parents=[common])
    a.add_argument("--name", required=True, metavar="NAME", help="project name (required)")
    a.add_argument("--desc", default="", metavar="TEXT", help="one-line description")
    a.add_argument("--start", default="", metavar="YYYY-MM-DD", help="start date")
    a.add_argument("--end", default="", metavar="YYYY-MM-DD", help="end date")
    a.add_argument("--goal", default="", metavar="TEXT", help="project goal / narrative")
    a.add_argument("--metrics", default="", metavar="TEXT", help="success metrics")
    a.add_argument("--scope-in", default="", metavar="TEXT", help="in scope")
    a.add_argument("--scope-out", default="", metavar="TEXT", help="out of scope")
    a.add_argument("--assumptions", default="", metavar="TEXT", help="assumptions")

    a = sub.add_parser("add-story", help="agent/human: add a story", parents=[common])
    a.add_argument("--project", type=int, required=True, metavar="ID", help="parent project id")
    a.add_argument("--title", required=True, metavar="TEXT", help="story title (required)")
    a.add_argument("--desc", default="", metavar="TEXT", help="description")
    a.add_argument("--start", default="", metavar="YYYY-MM-DD", help="start date")
    a.add_argument("--end", default="", metavar="YYYY-MM-DD", help="end date")
    a.add_argument("--owner", default="", metavar="NAME", help="owner (person or agent id)")
    a.add_argument(
        "--priority", choices=["p0", "p1", "p2", "p3"], default="", help="priority (p0 highest)"
    )
    a.add_argument("--labels", default="", metavar="A,B", help="comma-separated labels")
    a.add_argument("--estimate", default="", metavar="TEXT", help="rough estimate, e.g. 2w")
    a.add_argument(
        "--blocked-by", default="", metavar="IDS", help="comma-separated blocker story ids"
    )

    a = sub.add_parser("add-task", help="agent/human: add a task", parents=[common])
    a.add_argument("--story", type=int, required=True, metavar="ID", help="parent story id")
    a.add_argument("--title", required=True, metavar="TEXT", help="task title (required)")
    a.add_argument("--estimate", default="", metavar="TEXT", help="estimate, e.g. 2d")
    a.add_argument("--start", default="", metavar="YYYY-MM-DD", help="start date")
    a.add_argument("--end", default="", metavar="YYYY-MM-DD", help="end date")
    a.add_argument("--desc", default="", metavar="TEXT", help="description / context")
    a.add_argument("--owner", default="", metavar="NAME", help="owner (person or agent id)")
    a.add_argument(
        "--priority", choices=["p0", "p1", "p2", "p3"], default="", help="priority (p0 highest)"
    )
    a.add_argument("--labels", default="", metavar="A,B", help="comma-separated labels")
    a.add_argument(
        "--blocked-by", default="", metavar="IDS", help="comma-separated blocker task ids"
    )

    u = sub.add_parser(
        "update",
        help="edit title/desc/estimate/dates/narrative/owner/plan fields",
        parents=[common],
    )
    u.add_argument(
        "--kind", choices=["project", "story", "task"], required=True, help="what to edit"
    )
    u.add_argument("--id", type=int, required=True, metavar="ID", help="row id")
    u.add_argument("--title", default=None, metavar="TEXT", help="new title")
    u.add_argument("--name", default=None, metavar="NAME", help="alias of --title for projects")
    u.add_argument("--desc", default=None, metavar="TEXT", help="new description")
    u.add_argument("--estimate", default=None, metavar="TEXT", help="new estimate")
    u.add_argument("--start", default=None, metavar="YYYY-MM-DD", help="new start date")
    u.add_argument("--end", default=None, metavar="YYYY-MM-DD", help="new end date")
    u.add_argument("--owner", default=None, metavar="NAME", help="new owner (empty clears)")
    u.add_argument(
        "--priority",
        choices=["p0", "p1", "p2", "p3", "none"],
        default=None,
        help="new priority (`none` clears)",
    )
    u.add_argument("--labels", default=None, metavar="A,B", help="new labels (empty clears)")
    u.add_argument("--blocked-by", default=None, metavar="IDS", help="new blockers (empty clears)")
    u.add_argument("--goal", default=None, metavar="TEXT", help="new goal (projects)")
    u.add_argument("--metrics", default=None, metavar="TEXT", help="new metrics (projects)")
    u.add_argument("--scope-in", default=None, metavar="TEXT", help="new in-scope (projects)")
    u.add_argument("--scope-out", default=None, metavar="TEXT", help="new out-of-scope (projects)")
    u.add_argument("--assumptions", default=None, metavar="TEXT", help="new assumptions (projects)")

    sh = sub.add_parser(
        "show", help="full context record: fields + links + children", parents=[common]
    )
    sh.add_argument(
        "--kind", choices=["project", "story", "task"], required=True, help="what to show"
    )
    sh.add_argument("--id", type=int, required=True, metavar="ID", help="row id")

    al = sub.add_parser(
        "add-link", help="attach a supporting link to a story/task", parents=[common]
    )
    al.add_argument("--kind", choices=["story", "task"], required=True, help="parent kind")
    al.add_argument("--id", type=int, required=True, metavar="ID", help="parent id")
    al.add_argument("--url", required=True, metavar="URL", help="link URL (required)")
    al.add_argument("--label", default="", metavar="TEXT", help="short label")
    ll = sub.add_parser("links", help="list links on a story/task", parents=[common])
    ll.add_argument("--kind", choices=["story", "task"], required=True, help="parent kind")
    ll.add_argument("--id", type=int, required=True, metavar="ID", help="parent id")
    dl = sub.add_parser("delete-link", help="remove a link by its id", parents=[common])
    dl.add_argument("--id", type=int, required=True, metavar="ID", help="link id")

    ac = sub.add_parser("add-criteria", help="add an acceptance-checklist item", parents=[common])
    ac.add_argument("--kind", choices=["story", "task"], required=True, help="parent kind")
    ac.add_argument("--id", type=int, required=True, metavar="ID", help="parent id")
    ac.add_argument("--text", required=True, metavar="TEXT", help="criterion text (required)")
    lc = sub.add_parser("criteria", help="list acceptance criteria", parents=[common])
    lc.add_argument("--kind", choices=["story", "task"], required=True, help="parent kind")
    lc.add_argument("--id", type=int, required=True, metavar="ID", help="parent id")
    for _name, _help in (("check", "tick a criterion done"), ("uncheck", "reopen a criterion")):
        cc = sub.add_parser(_name, help=_help, parents=[common])
        cc.add_argument("--id", type=int, required=True, metavar="ID", help="criteria id")
    dc = sub.add_parser("delete-criteria", help="remove a criterion by its id", parents=[common])
    dc.add_argument("--id", type=int, required=True, metavar="ID", help="criteria id")

    ar = sub.add_parser("add-risk", help="register a project risk", parents=[common])
    ar.add_argument("--project", type=int, required=True, metavar="ID", help="project id")
    ar.add_argument("--title", required=True, metavar="TEXT", help="risk title (required)")
    ar.add_argument(
        "--likelihood",
        choices=["low", "med", "high"],
        default="med",
        help="likelihood (default: med)",
    )
    ar.add_argument(
        "--impact", choices=["low", "med", "high"], default="med", help="impact (default: med)"
    )
    ar.add_argument("--mitigation", default="", metavar="TEXT", help="mitigation plan")
    lr = sub.add_parser(
        "risks", help="list project risks (likelihood x impact first)", parents=[common]
    )
    lr.add_argument("--project", type=int, required=True, metavar="ID", help="project id")
    rs = sub.add_parser(
        "risk-status", help="move a risk open|mitigated|retired / set mitigation", parents=[common]
    )
    rs.add_argument("--id", type=int, required=True, metavar="ID", help="risk id")
    rs.add_argument(
        "--to", choices=["open", "mitigated", "retired"], default=None, help="new status"
    )
    rs.add_argument("--mitigation", default=None, metavar="TEXT", help="new mitigation text")

    am = sub.add_parser("add-milestone", help="add a dated timeline marker", parents=[common])
    am.add_argument("--project", type=int, required=True, metavar="ID", help="project id")
    am.add_argument("--title", required=True, metavar="TEXT", help="milestone title (required)")
    am.add_argument("--date", default="", metavar="YYYY-MM-DD", help="milestone date")
    lm = sub.add_parser("milestones", help="list project milestones", parents=[common])
    lm.add_argument("--project", type=int, required=True, metavar="ID", help="project id")
    dm = sub.add_parser("delete-milestone", help="remove a milestone by its id", parents=[common])
    dm.add_argument("--id", type=int, required=True, metavar="ID", help="milestone id")

    pr = sub.add_parser(
        "propose", help="agent: submit a story/task for human approval", parents=[common]
    )
    pr.add_argument("--kind", choices=["story", "task"], required=True, help="what to propose")
    pr.add_argument(
        "--parent",
        type=int,
        required=True,
        metavar="ID",
        help="project id (story) or story id (task)",
    )
    pr.add_argument("--title", required=True, metavar="TEXT", help="title (required)")
    pr.add_argument("--desc", default="", metavar="TEXT", help="description")
    pr.add_argument("--owner", default="", metavar="NAME", help="suggested owner")
    pr.add_argument(
        "--priority", choices=["p0", "p1", "p2", "p3"], default="", help="suggested priority"
    )
    pr.add_argument("--labels", default="", metavar="A,B", help="suggested labels")
    pr.add_argument("--estimate", default="", metavar="TEXT", help="suggested estimate")
    pr.add_argument("--start", default="", metavar="YYYY-MM-DD", help="suggested start")
    pr.add_argument("--end", default="", metavar="YYYY-MM-DD", help="suggested end")
    pr.add_argument("--blocked-by", default="", metavar="IDS", help="suggested blockers")
    pls = sub.add_parser("proposals", help="list proposals", parents=[common])
    pls.add_argument(
        "--status",
        choices=["pending", "approved", "rejected", "applied"],
        default=None,
        help="filter by status (default: all)",
    )
    ap = sub.add_parser("approve", help="approve a proposal (creates the item)", parents=[common])
    ap.add_argument("--id", type=int, required=True, metavar="ID", help="proposal id")
    rj = sub.add_parser("reject", help="reject a proposal", parents=[common])
    rj.add_argument("--id", type=int, required=True, metavar="ID", help="proposal id")

    ak = sub.add_parser("ask", help="agent: ask the human a question", parents=[common])
    ak.add_argument("--question", required=True, metavar="TEXT", help="question (required)")
    ql = sub.add_parser("questions", help="list questions", parents=[common])
    ql.add_argument("--all", action="store_true", help="include answered")
    an = sub.add_parser("answer", help="human: answer a question", parents=[common])
    an.add_argument("--id", type=int, required=True, metavar="ID", help="question id")
    an.add_argument("--text", required=True, metavar="TEXT", help="answer (required)")

    ex = sub.add_parser("export", help="full dump (agents: --format json)", parents=[common])
    ex.add_argument(
        "--format",
        choices=["json", "markdown"],
        default="json",
        help="output format (default: json)",
    )
    im = sub.add_parser("import", help="load an `lpui export --format json` dump", parents=[common])
    im.add_argument("--file", required=True, metavar="PATH", help="dump file (required)")
    sy = sub.add_parser("sync", help="snapshot SQLite -> Postgres replica (S#5)", parents=[common])
    sy.add_argument(
        "--dsn",
        default="",
        metavar="DSN",
        help="postgresql://user:pass@host:port/db (or $LAZYPLAN_PG_DSN)",
    )

    s = sub.add_parser("status", help="move project/story/task to a status", parents=[common])
    s.add_argument(
        "--kind", choices=["project", "story", "task"], required=True, help="what to move"
    )
    s.add_argument("--id", type=int, required=True, metavar="ID", help="row id")
    s.add_argument(
        "--to", choices=[v.value for v in Status], required=True, help="new status (required)"
    )

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
