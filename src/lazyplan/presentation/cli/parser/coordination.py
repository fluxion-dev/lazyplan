"""Argument groups for coordination commands."""

from __future__ import annotations

import argparse

from ....core.kinds import KINDS
from .common import plan_id_arg


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
    cl.add_argument("--worktree", default="", metavar="PATH", help="checkout being worked")
    cl.add_argument("--repo", default="", metavar="PATH", help="shared repo root")
    cl.add_argument(
        "--reason", default="", metavar="TEXT", help="why a worktree gate is overridden"
    )


def _lease_list(
    sub: argparse._SubParsersAction[argparse.ArgumentParser],
    common: argparse.ArgumentParser,
    *,
    name: str,
    blurb: str,
) -> None:
    """One claims-shaped command: plan filter plus the expired toggle."""
    parser = sub.add_parser(name, help=blurb, parents=[common])
    plan_id_arg(parser, help="only this plan")
    parser.add_argument("--all", action="store_true", help="include expired claims")


def add_claims(
    sub: argparse._SubParsersAction[argparse.ArgumentParser], common: argparse.ArgumentParser
) -> None:
    _lease_list(sub, common, name="claims", blurb="list active task leases with holder and expiry")


def add_next(
    sub: argparse._SubParsersAction[argparse.ArgumentParser], common: argparse.ArgumentParser
) -> None:

    nxt = sub.add_parser(
        "next",
        help="claim the next eligible task and move it doing",
        parents=[common],
    )
    plan_id_arg(nxt, help="only this plan")
    nxt.add_argument("--ttl", default="", metavar="TIME", help="lease length, e.g. 30m or 2.hours")
    nxt.add_argument("--note", default="", metavar="TEXT", help="note stored on the claim")
    nxt.add_argument(
        "--lane",
        type=int,
        default=None,
        metavar="ID",
        help="only claim a task in this lane milestone",
    )
    nxt.add_argument(
        "--suggest", action="store_true", help="show the next task without claiming it"
    )
    nxt.add_argument("--force", action="store_true", help="override a worktree gate")
    nxt.add_argument(
        "--reason", default="", metavar="TEXT", help="why a worktree gate is overridden"
    )


def add_dispatch(
    sub: argparse._SubParsersAction[argparse.ArgumentParser], common: argparse.ArgumentParser
) -> None:

    dp = sub.add_parser(
        "dispatch",
        help="show plan lanes, waves, capacity, and worker prompts",
        parents=[common],
    )
    plan_id_arg(dp, help="plan to dispatch", required=True)
    dp.add_argument("--lane", type=int, default=None, metavar="ID", help="one lane milestone")
    dp.add_argument(
        "--max-chars",
        type=int,
        default=4000,
        metavar="N",
        help="prompt budget in characters (default: 4000)",
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
        choices=["add", "list", "edit", "resolve", "unresolve"],
        help="comment action",
    )
    co.add_argument(
        "--kind", choices=list(KINDS), default=None, help="which row the comment belongs to"
    )
    co.add_argument("--id", type=int, default=None, metavar="ID", help="row id")
    co.add_argument(
        "--comment", type=int, default=None, metavar="ID", help="comment id (edit/resolve only)"
    )
    co.add_argument("--text", default=None, metavar="TEXT", help="comment text (add/edit only)")
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
    plan_id_arg(sh, help="plan to share", required=True)
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
    plan_id_arg(au, help="audit one plan")
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
    au.add_argument(
        "--min-evidence",
        type=float,
        default=0.0,
        metavar="RATIO",
        help="strict-mode minimum criteria with passing evidence; 0 disables (default: 0)",
    )


def _packet_command(
    sub: argparse._SubParsersAction[argparse.ArgumentParser],
    common: argparse.ArgumentParser,
    *,
    name: str,
    blurb: str,
    plan_help: str,
) -> None:
    """One review-packet command: plan choice plus a Markdown length cap."""
    parser = sub.add_parser(name, help=blurb, parents=[common])
    parser.add_argument("--plan", type=int, default=None, metavar="ID", help=plan_help)
    parser.add_argument(
        "--max-chars", type=int, default=0, metavar="N", help="cap the Markdown length"
    )


def add_review(
    sub: argparse._SubParsersAction[argparse.ArgumentParser], common: argparse.ArgumentParser
) -> None:
    _packet_command(
        sub,
        common,
        name="review",
        blurb="print one deterministic review packet",
        plan_help="review one plan (default: active)",
    )


def add_ship(
    sub: argparse._SubParsersAction[argparse.ArgumentParser], common: argparse.ArgumentParser
) -> None:
    _packet_command(
        sub,
        common,
        name="ship",
        blurb="print one deterministic outcome ship note",
        plan_help="ship one plan (default: active)",
    )


def add_brief(
    sub: argparse._SubParsersAction[argparse.ArgumentParser], common: argparse.ArgumentParser
) -> None:

    br = sub.add_parser(
        "brief",
        help="show the active plan, the next task, and unlinked commits",
        parents=[common],
    )
    plan_id_arg(br, help="brief one plan")


def add_context(
    sub: argparse._SubParsersAction[argparse.ArgumentParser], common: argparse.ArgumentParser
) -> None:

    ct = sub.add_parser(
        "context",
        help="show the budgeted session context packet",
        parents=[common],
    )
    plan_id_arg(ct, help="context one plan")
    ct.add_argument(
        "--max-chars",
        type=int,
        default=4000,
        metavar="N",
        help="packet budget in characters (default: 4000, minimum: 120)",
    )


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
    plan_id_arg(li, help="plan to lint", required=True)
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
        help="read a host lifecycle event, track the session, and print a reminder",
        parents=[common],
    )
    hk.add_argument(
        "event",
        nargs="?",
        default=None,
        choices=[
            "session-start",
            "prompt-submit",
            "pre-tool",
            "post-tool",
            "stop",
            "session-end",
            "pre-compact",
        ],
        help="which lifecycle event fired",
    )
    hk.add_argument(
        "--check",
        action="store_true",
        help="read-only hook readiness probe; writes nothing",
    )
    hk.add_argument(
        "--host",
        choices=["opencode", "claude", "gemini", "codex", "cursor"],
        default="",
        help="host emitting the event (inferred from the payload when omitted)",
    )
    hk.add_argument(
        "--mode",
        choices=["strict", "advisory", "off"],
        default="strict",
        help="installed behavior mode; LAZYPLAN_HOOKS overrides it at runtime",
    )
    hk.add_argument(
        "--command",
        default="",
        help=argparse.SUPPRESS,
    )
    hk.add_argument(
        "--tool",
        default="",
        help=argparse.SUPPRESS,
    )
    hk.add_argument(
        "--path",
        default="",
        help=argparse.SUPPRESS,
    )
    hk.add_argument(
        "--host-session",
        default="",
        help=argparse.SUPPRESS,
    )
    for option in ("--agent", "--model", "--role", "--parent-session", "--pid"):
        hk.add_argument(option, default="", help=argparse.SUPPRESS)


def add_who(
    sub: argparse._SubParsersAction[argparse.ArgumentParser], common: argparse.ArgumentParser
) -> None:
    _lease_list(sub, common, name="who", blurb="alias for `claims`: active task leases")
