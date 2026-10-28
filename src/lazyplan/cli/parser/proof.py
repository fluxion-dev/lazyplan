"""Argument groups for proof commands."""

from __future__ import annotations

import argparse

from ...kinds import KINDS


def add_link(
    sub: argparse._SubParsersAction[argparse.ArgumentParser], common: argparse.ArgumentParser
) -> None:

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


def add_unlink(
    sub: argparse._SubParsersAction[argparse.ArgumentParser], common: argparse.ArgumentParser
) -> None:

    ul = sub.add_parser("unlink", help="detach a git commit from a row", parents=[common])
    ul.add_argument(
        "--kind",
        choices=list(KINDS),
        required=True,
        help="which kind of row to detach from",
    )
    ul.add_argument("--id", type=int, required=True, metavar="ID", help="id of the row")
    ul.add_argument("--sha", required=True, metavar="SHA", help="which commit to detach (required)")


def add_commits(
    sub: argparse._SubParsersAction[argparse.ArgumentParser], common: argparse.ArgumentParser
) -> None:

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


def add_link_repo(
    sub: argparse._SubParsersAction[argparse.ArgumentParser], common: argparse.ArgumentParser
) -> None:

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


def add_unlink_repo(
    sub: argparse._SubParsersAction[argparse.ArgumentParser], common: argparse.ArgumentParser
) -> None:

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


def add_repos(
    sub: argparse._SubParsersAction[argparse.ArgumentParser], common: argparse.ArgumentParser
) -> None:

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


def add_export(
    sub: argparse._SubParsersAction[argparse.ArgumentParser], common: argparse.ArgumentParser
) -> None:

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


def add_import(
    sub: argparse._SubParsersAction[argparse.ArgumentParser], common: argparse.ArgumentParser
) -> None:

    im = sub.add_parser(
        "import", help="load a file saved by `lpui export --format json`", parents=[common]
    )
    im.add_argument(
        "--file", required=True, metavar="PATH", help="the saved file to load (required)"
    )


def add_feed(
    sub: argparse._SubParsersAction[argparse.ArgumentParser], common: argparse.ArgumentParser
) -> None:

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


def add_watch(
    sub: argparse._SubParsersAction[argparse.ArgumentParser], common: argparse.ArgumentParser
) -> None:

    w = sub.add_parser("watch", help="same as feed --follow", parents=[common])
    w.add_argument(
        "--limit",
        type=int,
        default=20,
        metavar="N",
        help="how many recent events to show (default: 20)",
    )
