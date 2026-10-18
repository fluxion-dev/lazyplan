"""`lp` argument parser (every verb the CLI and TUI command bar share)."""

from __future__ import annotations

import argparse
import os

from .models import Status


def build_parser() -> argparse.ArgumentParser:
    """lp argument parser; globals repeat on every subcommand."""
    p = argparse.ArgumentParser(prog="lp", description="lazyplan: projects > stories > tasks")
    p.add_argument(
        "--db",
        default=None,
        help="sqlite path (default: $LAZYPLAN_DB, else ./.plan/ in repo, else global)",
    )
    p.add_argument("--json", action="store_true", help="agent-friendly JSON output")
    p.add_argument(
        "--actor",
        default=os.environ.get("USER", "human"),
        help="who is making this change (surfaced in feed)",
    )
    # repeat globals on subcommands so `lp list --json` works as well as `lp --json list`.
    # SUPPRESS defaults: an explicit global flag must survive when the
    # subcommand flag is absent (argparse would otherwise let the
    # subcommand default clobber it).
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--json", action="store_true", default=argparse.SUPPRESS, help="agent-friendly JSON output"
    )
    common.add_argument("--actor", default=argparse.SUPPRESS)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="init .plan/ in this repo (or global db)", parents=[common])
    sub.add_parser("seed", help="insert demo project/stories/tasks", parents=[common])
    sub.add_parser("info", help="show resolved db path, repo root, counts", parents=[common])
    li = sub.add_parser("list", help="ascii tree of projects > stories > tasks", parents=[common])
    li.add_argument("--status", choices=[v.value for v in Status], default=None)
    li.add_argument("--project", type=int, default=None)
    li.add_argument("--owner", default=None)
    li.add_argument("--priority", choices=["p0", "p1", "p2", "p3"], default=None)
    g = sub.add_parser("gantt", help="ascii gantt of stories (+tasks)", parents=[common])
    g.add_argument("--width", type=int, default=40)
    g.add_argument("--status", choices=[v.value for v in Status], default=None)
    g.add_argument("--project", type=int, default=None)
    g.add_argument("--owner", default=None)
    g.add_argument("--priority", choices=["p0", "p1", "p2", "p3"], default=None)
    g.add_argument("--tasks", action="store_true", help="also render task bars")

    a = sub.add_parser("add-project", help="agent/human: add a project", parents=[common])
    a.add_argument("--name", required=True)
    a.add_argument("--desc", default="")
    a.add_argument("--start", default="")
    a.add_argument("--end", default="")
    a.add_argument("--goal", default="")
    a.add_argument("--metrics", default="")
    a.add_argument("--scope-in", default="")
    a.add_argument("--scope-out", default="")
    a.add_argument("--assumptions", default="")

    a = sub.add_parser("add-story", help="agent/human: add a story", parents=[common])
    a.add_argument("--project", type=int, required=True)
    a.add_argument("--title", required=True)
    a.add_argument("--desc", default="")
    a.add_argument("--start", default="")
    a.add_argument("--end", default="")
    a.add_argument("--owner", default="")
    a.add_argument("--priority", choices=["p0", "p1", "p2", "p3"], default="")
    a.add_argument("--labels", default="")
    a.add_argument("--estimate", default="")
    a.add_argument("--blocked-by", default="")

    a = sub.add_parser("add-task", help="agent/human: add a task", parents=[common])
    a.add_argument("--story", type=int, required=True)
    a.add_argument("--title", required=True)
    a.add_argument("--estimate", default="")
    a.add_argument("--start", default="")
    a.add_argument("--end", default="")
    a.add_argument("--desc", default="")
    a.add_argument("--owner", default="")
    a.add_argument("--priority", choices=["p0", "p1", "p2", "p3"], default="")
    a.add_argument("--labels", default="")
    a.add_argument("--blocked-by", default="")

    u = sub.add_parser(
        "update",
        help="edit title/desc/estimate/dates/narrative/owner/plan fields",
        parents=[common],
    )
    u.add_argument("--kind", choices=["project", "story", "task"], required=True)
    u.add_argument("--id", type=int, required=True)
    u.add_argument("--title", default=None)
    u.add_argument("--name", default=None, help="alias of --title for projects")
    u.add_argument("--desc", default=None)
    u.add_argument("--estimate", default=None)
    u.add_argument("--start", default=None)
    u.add_argument("--end", default=None)
    u.add_argument("--owner", default=None)
    u.add_argument("--priority", choices=["p0", "p1", "p2", "p3", "none"], default=None)
    u.add_argument("--labels", default=None)
    u.add_argument("--blocked-by", default=None)
    u.add_argument("--goal", default=None)
    u.add_argument("--metrics", default=None)
    u.add_argument("--scope-in", default=None)
    u.add_argument("--scope-out", default=None)
    u.add_argument("--assumptions", default=None)

    sh = sub.add_parser(
        "show", help="full context record: fields + links + children", parents=[common]
    )
    sh.add_argument("--kind", choices=["project", "story", "task"], required=True)
    sh.add_argument("--id", type=int, required=True)

    al = sub.add_parser(
        "add-link", help="attach a supporting link to a story/task", parents=[common]
    )
    al.add_argument("--kind", choices=["story", "task"], required=True)
    al.add_argument("--id", type=int, required=True)
    al.add_argument("--url", required=True)
    al.add_argument("--label", default="")
    ll = sub.add_parser("links", help="list links on a story/task", parents=[common])
    ll.add_argument("--kind", choices=["story", "task"], required=True)
    ll.add_argument("--id", type=int, required=True)
    dl = sub.add_parser("delete-link", help="remove a link by its id", parents=[common])
    dl.add_argument("--id", type=int, required=True)

    ac = sub.add_parser("add-criteria", help="add an acceptance-checklist item", parents=[common])
    ac.add_argument("--kind", choices=["story", "task"], required=True)
    ac.add_argument("--id", type=int, required=True)
    ac.add_argument("--text", required=True)
    lc = sub.add_parser("criteria", help="list acceptance criteria", parents=[common])
    lc.add_argument("--kind", choices=["story", "task"], required=True)
    lc.add_argument("--id", type=int, required=True)
    for _name, _help in (("check", "tick a criterion done"), ("uncheck", "reopen a criterion")):
        cc = sub.add_parser(_name, help=_help, parents=[common])
        cc.add_argument("--id", type=int, required=True)
    dc = sub.add_parser("delete-criteria", help="remove a criterion by its id", parents=[common])
    dc.add_argument("--id", type=int, required=True)

    ar = sub.add_parser("add-risk", help="register a project risk", parents=[common])
    ar.add_argument("--project", type=int, required=True)
    ar.add_argument("--title", required=True)
    ar.add_argument("--likelihood", choices=["low", "med", "high"], default="med")
    ar.add_argument("--impact", choices=["low", "med", "high"], default="med")
    ar.add_argument("--mitigation", default="")
    lr = sub.add_parser(
        "risks", help="list project risks (likelihood x impact first)", parents=[common]
    )
    lr.add_argument("--project", type=int, required=True)
    rs = sub.add_parser(
        "risk-status", help="move a risk open|mitigated|retired / set mitigation", parents=[common]
    )
    rs.add_argument("--id", type=int, required=True)
    rs.add_argument("--to", choices=["open", "mitigated", "retired"], default=None)
    rs.add_argument("--mitigation", default=None)

    am = sub.add_parser("add-milestone", help="add a dated timeline marker", parents=[common])
    am.add_argument("--project", type=int, required=True)
    am.add_argument("--title", required=True)
    am.add_argument("--date", default="")
    lm = sub.add_parser("milestones", help="list project milestones", parents=[common])
    lm.add_argument("--project", type=int, required=True)
    dm = sub.add_parser("delete-milestone", help="remove a milestone by its id", parents=[common])
    dm.add_argument("--id", type=int, required=True)

    pr = sub.add_parser(
        "propose", help="agent: submit a story/task for human approval", parents=[common]
    )
    pr.add_argument("--kind", choices=["story", "task"], required=True)
    pr.add_argument(
        "--parent", type=int, required=True, help="project id (story) or story id (task)"
    )
    pr.add_argument("--title", required=True)
    pr.add_argument("--desc", default="")
    pr.add_argument("--owner", default="")
    pr.add_argument("--priority", choices=["p0", "p1", "p2", "p3"], default="")
    pr.add_argument("--labels", default="")
    pr.add_argument("--estimate", default="")
    pr.add_argument("--start", default="")
    pr.add_argument("--end", default="")
    pr.add_argument("--blocked-by", default="")
    pls = sub.add_parser("proposals", help="list proposals", parents=[common])
    pls.add_argument(
        "--status", choices=["pending", "approved", "rejected", "applied"], default=None
    )
    ap = sub.add_parser("approve", help="approve a proposal (creates the item)", parents=[common])
    ap.add_argument("--id", type=int, required=True)
    rj = sub.add_parser("reject", help="reject a proposal", parents=[common])
    rj.add_argument("--id", type=int, required=True)

    ak = sub.add_parser("ask", help="agent: ask the human a question", parents=[common])
    ak.add_argument("--question", required=True)
    ql = sub.add_parser("questions", help="list questions", parents=[common])
    ql.add_argument("--all", action="store_true", help="include answered")
    an = sub.add_parser("answer", help="human: answer a question", parents=[common])
    an.add_argument("--id", type=int, required=True)
    an.add_argument("--text", required=True)

    ex = sub.add_parser("export", help="full dump (agents: --format json)", parents=[common])
    ex.add_argument("--format", choices=["json", "markdown"], default="json")
    im = sub.add_parser("import", help="load an `lp export --format json` dump", parents=[common])
    im.add_argument("--file", required=True)
    sy = sub.add_parser("sync", help="snapshot SQLite -> Postgres replica (S#5)", parents=[common])
    sy.add_argument(
        "--dsn", default="", help="postgresql://user:pass@host:port/db (or $LAZYPLAN_PG_DSN)"
    )

    s = sub.add_parser("status", help="move project/story/task to a status", parents=[common])
    s.add_argument("--kind", choices=["project", "story", "task"], required=True)
    s.add_argument("--id", type=int, required=True)
    s.add_argument("--to", choices=[v.value for v in Status], required=True)

    d = sub.add_parser("delete", help="delete a project/story/task", parents=[common])
    d.add_argument("--kind", choices=["project", "story", "task"], required=True)
    d.add_argument("--id", type=int, required=True)

    f = sub.add_parser("feed", help="recent agent/human activity", parents=[common])
    f.add_argument("--limit", type=int, default=20)
    f.add_argument("--follow", action="store_true", help="tail new events")
    f.add_argument("--interval", type=float, default=1.0)
    sub.add_parser("watch", help="alias of feed --follow", parents=[common]).add_argument(
        "--limit", type=int, default=20
    )

    c = sub.add_parser("completion", help="shell completions", parents=[common])
    c.add_argument("--shell", choices=["bash", "zsh"], required=True)

    sub.add_parser("help", help="print shared help text (same as TUI ?)", parents=[common])
    sub.add_parser("ui", help="launch Textual TUI")
    return p
