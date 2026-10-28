"""Forge CLI commands: pull request reads and auth."""

from __future__ import annotations

import argparse
import sys

from ... import (
    porcelain,
    services,
)
from ...design import (
    msg_error,
    msg_not_found,
)
from ...forge import parse_pull_url, resolve_auth
from ...render import (
    render_forge_links,
    render_forge_status,
)
from ...store import Store
from ..emit import (
    _emit,
    _emit_read,
    _emit_record,
)
from ..rows_proof import (
    _pr_row,
    _pr_status_rows,
)


def _cmd_pr_auth(store: Store, args: argparse.Namespace, actor: str) -> int:
    auth = resolve_auth()
    payload = {
        "provider": "github",
        "source": auth.source,
        "available": auth.available,
    }
    if args.json:
        return _emit(args, payload)
    if auth.available:
        print(f"github auth: {auth.source}")
    else:
        print("github auth: none (set GITHUB_TOKEN or run `gh auth login`)")
    return 0


def _cmd_pr_status(store: Store, args: argparse.Namespace, actor: str) -> int:
    if args.kind or args.id:
        if not (args.kind and args.id):
            print(msg_error(ValueError("--kind and --id go together")), file=sys.stderr)
            return 2
        if store.get_parent(args.kind, args.id) is None:
            print(msg_not_found(args.kind, args.id), file=sys.stderr)
            return 1
    auth = resolve_auth()
    entries = services.forge_statuses(
        store,
        kind=str(args.kind) if args.kind else "",
        obj_id=args.id or 0,
        repo_path=str(args.repo) if args.repo else "",
        auth=auth,
    )
    parent = f"{args.kind}:{args.id}" if args.kind and args.id else "-"
    return _emit_read(
        args,
        entries,
        _pr_status_rows(entries, parent),
        render_forge_status(entries) if entries else "",
        "(no linked repos)",
    )


def _cmd_pr_list(store: Store, args: argparse.Namespace, actor: str) -> int:
    if store.get_parent(args.kind, args.id) is None:
        print(msg_not_found(args.kind, args.id), file=sys.stderr)
        return 1
    links = store.list_forge_links(args.kind, args.id)
    parent = f"{args.kind}:{args.id}"
    return _emit_read(
        args,
        [vars(link) for link in links],
        [_pr_row(vars(link), parent) for link in links],
        render_forge_links([vars(link) for link in links]) if links else "",
        "(no pull requests linked)",
    )


def _cmd_pr_show(store: Store, args: argparse.Namespace, actor: str) -> int:
    if store.get_parent(args.kind, args.id) is None:
        print(msg_not_found(args.kind, args.id), file=sys.stderr)
        return 1
    links = [
        link for link in store.list_forge_links(args.kind, args.id) if link.number == args.number
    ]
    if not links:
        print(msg_not_found("pull request", args.number), file=sys.stderr)
        return 1
    link = vars(links[0])
    return _emit_read(
        args,
        link,
        [_pr_row(link, f"{args.kind}:{args.id}")],
        render_forge_links([link]),
    )


def _cmd_pr_link(store: Store, args: argparse.Namespace, actor: str) -> int:
    if store.get_parent(args.kind, args.id) is None:
        print(msg_not_found(args.kind, args.id), file=sys.stderr)
        return 1
    parsed = parse_pull_url(str(args.url))
    if parsed is None:
        print(
            msg_error(ValueError(f"not a GitHub pull request URL: {args.url!r}")), file=sys.stderr
        )
        return 2
    ref, number = parsed
    state = str(args.state) if args.state else ""
    title = str(args.title) if args.title else f"PR #{number}"
    link = store.link_forge(
        args.kind,
        args.id,
        number,
        provider="github",
        kind="pull",
        url=str(args.url),
        title=title,
        state=state,
        payload=f'{{"repository": "{ref.owner}/{ref.repo}"}}',
        actor=actor,
    )
    line = porcelain.row("pr", link.number, "linked", link.url, f"{args.kind}:{args.id}", "-")
    return _emit_record(args, line, {"link": vars(link)})


def _cmd_pr_unlink(store: Store, args: argparse.Namespace, actor: str) -> int:
    if store.get_parent(args.kind, args.id) is None:
        print(msg_not_found(args.kind, args.id), file=sys.stderr)
        return 1
    ok = store.unlink_forge(args.kind, args.id, args.number, actor=actor)
    if not ok:
        print(msg_not_found("pull request", args.number), file=sys.stderr)
        return 1
    line = porcelain.row("pr", args.number, "unlinked", "-", f"{args.kind}:{args.id}", "-")
    return _emit_record(args, line, {"ok": True, "unlinked": f"PR #{args.number}"})


def _cmd_pr_refresh(store: Store, args: argparse.Namespace, actor: str) -> int:
    if store.get_parent(args.kind, args.id) is None:
        print(msg_not_found(args.kind, args.id), file=sys.stderr)
        return 1
    stats = services.refresh_forge(store, args.kind, args.id, actor=actor)
    for error in stats["errors"]:
        ref = str(error.get("sha") or error.get("branch") or error.get("merge_commit") or "refresh")
        if error.get("sha"):
            ref = ref[:12]
        print(f"warning: {ref}: {error.get('error', '')}", file=sys.stderr)
    if args.json:
        return _emit(args, stats)
    print(
        f"linked {stats['linked']} PRs from {stats['commits']} commits and "
        f"{stats['branches']} branches ({stats['merges']} merges, "
        f"{stats['stale']} cached, {stats['skipped']} skipped)"
    )
    return 0 if stats["linked"] or not stats["errors"] else 1
