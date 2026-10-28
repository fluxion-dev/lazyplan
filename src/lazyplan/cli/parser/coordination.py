"""Argument groups for coordination commands."""

from __future__ import annotations

import argparse

from ...kinds import KINDS


def add_claim(
    sub: argparse._SubParsersAction[argparse.ArgumentParser], common: argparse.ArgumentParser
) -> None:

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


def add_claims(
    sub: argparse._SubParsersAction[argparse.ArgumentParser], common: argparse.ArgumentParser
) -> None:

    cls = sub.add_parser(
        "claims",
        help="list active task leases with holder and expiry",
        parents=[common],
    )
    cls.add_argument("--plan", type=int, default=None, metavar="ID", help="only this plan")
    cls.add_argument("--all", action="store_true", help="include expired claims")


def add_next(
    sub: argparse._SubParsersAction[argparse.ArgumentParser], common: argparse.ArgumentParser
) -> None:

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


def add_note(
    sub: argparse._SubParsersAction[argparse.ArgumentParser], common: argparse.ArgumentParser
) -> None:

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


def add_comment(
    sub: argparse._SubParsersAction[argparse.ArgumentParser], common: argparse.ArgumentParser
) -> None:

    co = sub.add_parser(
        "comment",
        help="add, list, resolve, or unresolve review comments",
        parents=[common],
    )
    co.add_argument(
        "action",
        choices=["add", "list", "resolve", "unresolve"],
        help="comment action",
    )
    co.add_argument(
        "--kind", choices=list(KINDS), default=None, help="which row the comment belongs to"
    )
    co.add_argument("--id", type=int, default=None, metavar="ID", help="row id")
    co.add_argument(
        "--comment", type=int, default=None, metavar="ID", help="comment id (resolve only)"
    )
    co.add_argument("--text", default=None, metavar="TEXT", help="comment text (add only)")
    co.add_argument(
        "--mentions",
        default=None,
        metavar="NAME",
        help="only comments that mention @NAME (list only)",
    )


def add_share(
    sub: argparse._SubParsersAction[argparse.ArgumentParser], common: argparse.ArgumentParser
) -> None:

    sh = sub.add_parser(
        "share",
        help="write a read-only HTML or JSON plan snapshot",
        parents=[common],
    )
    sh.add_argument("--plan", type=int, required=True, metavar="ID", help="plan to share")
    sh.add_argument("--format", choices=["html", "json"], default="html", help="snapshot format")
    sh.add_argument("--out", default=None, metavar="PATH", help="write to a file")


def add_sync(
    sub: argparse._SubParsersAction[argparse.ArgumentParser], common: argparse.ArgumentParser
) -> None:

    sy = sub.add_parser(
        "sync",
        help="merge plans from a JSON dump by stable uid",
        parents=[common],
    )
    sy.add_argument("--file", required=True, metavar="PATH", help="export dump to merge")
    sy.add_argument("--dry-run", action="store_true", help="report without writing")


def add_mcp(
    sub: argparse._SubParsersAction[argparse.ArgumentParser], common: argparse.ArgumentParser
) -> None:

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


def add_audit(
    sub: argparse._SubParsersAction[argparse.ArgumentParser], common: argparse.ArgumentParser
) -> None:

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


def add_brief(
    sub: argparse._SubParsersAction[argparse.ArgumentParser], common: argparse.ArgumentParser
) -> None:

    br = sub.add_parser(
        "brief",
        help="show the active plan, the next task, and unlinked commits",
        parents=[common],
    )
    br.add_argument("--plan", type=int, default=None, metavar="ID", help="brief one plan")


def add_stats(
    sub: argparse._SubParsersAction[argparse.ArgumentParser], common: argparse.ArgumentParser
) -> None:

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


def add_lint(
    sub: argparse._SubParsersAction[argparse.ArgumentParser], common: argparse.ArgumentParser
) -> None:

    li = sub.add_parser(
        "lint",
        help="lint a plan for traceability and task-quality gaps",
        parents=[common],
    )
    li.add_argument("--plan", type=int, required=True, metavar="ID", help="plan to lint")
    li.add_argument("--strict", action="store_true", help="exit 2 when any finding exists")


def add_trace(
    sub: argparse._SubParsersAction[argparse.ArgumentParser], common: argparse.ArgumentParser
) -> None:

    tr = sub.add_parser(
        "trace",
        help="trace acceptance criteria to tasks, commits, and pull requests",
        parents=[common],
    )
    group = tr.add_mutually_exclusive_group(required=True)
    group.add_argument("--plan", type=int, metavar="ID", help="trace a whole plan's criteria")
    group.add_argument("--criterion", type=int, metavar="ID", help="trace one criterion")


def add_hook(
    sub: argparse._SubParsersAction[argparse.ArgumentParser], common: argparse.ArgumentParser
) -> None:

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


def add_who(
    sub: argparse._SubParsersAction[argparse.ArgumentParser], common: argparse.ArgumentParser
) -> None:

    who = sub.add_parser(
        "who",
        help="alias for `claims`: active task leases",
        parents=[common],
    )
    who.add_argument("--plan", type=int, default=None, metavar="ID", help="only this plan")
    who.add_argument("--all", action="store_true", help="include expired claims")
