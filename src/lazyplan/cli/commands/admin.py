"""Administrative CLI commands: sync, share, MCP, hooks, and upgrade."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from ... import (
    porcelain,
    textfile,
)
from ...design import (
    EMPTY_FEED,
    HELP_TEXT,
    msg_error,
    msg_not_found,
)
from ...repo import find_repo_root, repo_label, resolve_db_path
from ...seed import seed as seed_demo
from ...store import Store
from ...upgrade import (
    UpgradeError,
    detect,
    guard_message,
    latest_version,
    parse_version,
    run_upgrade,
)
from ..emit import (
    _emit,
)
from ..parser import build_parser, package_version
from ..rows_proof import (
    _feed_row,
    _info_rows,
)


def _cmd_sync(store: Store, args: argparse.Namespace, actor: str) -> int:
    from ... import sync as sync_mod

    try:
        data = json.loads(textfile.read(args.file))
        report = sync_mod.sync(store, data, actor=actor, dry_run=bool(args.dry_run))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(msg_error(exc), file=sys.stderr)
        return 2
    if args.json:
        _emit(args, report)
    elif porcelain.enabled(args):
        for item in report["added"]:
            print(porcelain.row("sync", item["uid"] or "-", "add", item["title"], "-", "added"))
        for item in report["skipped"]:
            print(
                porcelain.row(
                    "sync",
                    item["uid"] or "-",
                    "skip",
                    item["title"],
                    f"plan:{item['local_id']}",
                    "identical",
                )
            )
        for item in report["conflicts"]:
            print(
                porcelain.row(
                    "sync",
                    item["uid"] or "-",
                    "conflict",
                    item["title"],
                    f"plan:{item['local_id']}" if item["local_id"] else "-",
                    ",".join(item["differences"]),
                )
            )
    else:
        print(
            f"{'dry-run: ' if report['dry_run'] else ''}"
            f"{len(report['added'])} added · {len(report['skipped'])} skipped · "
            f"{len(report['conflicts'])} conflicts"
        )
        for item in report["conflicts"]:
            print(
                f"  conflict {item['title']} ({item['uid'] or '-'}): "
                f"{', '.join(item['differences'])}"
            )
    return 1 if report["conflicts"] else 0


def _cmd_share(store: Store, args: argparse.Namespace, actor: str) -> int:
    from ... import share as share_mod

    del actor
    if store.get_plan(args.plan) is None:
        print(msg_not_found("plan", args.plan), file=sys.stderr)
        return 1
    text = share_mod.write(store, args.plan, args.format, args.out)
    if text is None:
        print(msg_not_found("plan", args.plan), file=sys.stderr)
        return 1
    if args.out:
        if args.json:
            return _emit(args, {"shared": args.out, "format": args.format})
        print(f"shared P{args.plan} as {args.format}: {args.out}")
        return 0
    print(text, end="" if text.endswith("\n") else "\n")
    return 0


def _cmd_mcp(store: Store | None, args: argparse.Namespace, actor: str) -> int:
    from ... import mcp as mcp_mod

    del store
    path = resolve_db_path(args.db)
    return mcp_mod.run(str(path), actor=actor, read_only=bool(args.read_only))


def _cmd_hook(store: Store | None, args: argparse.Namespace, actor: str) -> int:
    """Read-only lifecycle reminder; always exits 0 so a host never blocks."""
    from ... import hook_hosts, hooks

    del store, actor
    payload = hooks.read_payload(sys.stdin)
    host = hooks.detect_host(payload, args.host)
    result = hooks.run(args.event, payload, host, Path.cwd())
    if args.json:
        _emit(
            args,
            {
                "event": args.event,
                "host": host,
                "text": result.text,
                "context": result.context,
            },
        )
        return 0
    rendered = hook_hosts.render(host, args.event, result)
    if rendered:
        print(rendered)
    return 0


def _cmd_info(store: Store, args: argparse.Namespace, actor: str) -> int:
    root = find_repo_root(Path.cwd())
    plan_dir = store.path.parent
    try:
        contents = sorted(f.name for f in plan_dir.iterdir()) if plan_dir.is_dir() else []
    except OSError:
        contents = []
    payload = {
        "db": str(store.path),
        "repo": str(root) if root else None,
        "scope": repo_label(store.path),
        "plan_files": contents,
        "counts": store.counts(),
    }
    if porcelain.enabled(args):
        for line in _info_rows(payload):
            print(line)
        return 0
    return _emit(args, payload)


def _cmd_seed(store: Store, args: argparse.Namespace, actor: str) -> int:
    seed_demo(store)
    return _emit(args, {"db": str(store.path), "counts": store.counts()})


def _print_feed_events(
    events: list[dict], terse: bool, *, reverse: bool = False, flush: bool = False
) -> None:
    """Print feed events in one format; callers choose order and buffering."""
    items = reversed(events) if reverse else events
    for event in items:
        if terse:
            print(_feed_row(event), flush=flush)
        else:
            print(
                f"#{event['id']} [{event['actor']}] "
                f"{event['kind']}/{event['action']}: {event['detail']}",
                flush=flush,
            )


def _cmd_feed(store: Store, args: argparse.Namespace, actor: str) -> int:
    seen = -1
    terse = porcelain.enabled(args)
    while True:
        events = store.feed(args.limit)
        if not args.follow:
            if args.json:
                print(json.dumps(events, indent=2, default=str))
            else:
                if not events and not terse:
                    print(EMPTY_FEED)
                _print_feed_events(events, terse, reverse=True)
            return 0
        fresh = [event for event in events if event["id"] > seen]
        if args.json:
            for event in reversed(fresh):
                print(json.dumps(event, default=str))
        else:
            _print_feed_events(fresh, terse, reverse=True, flush=True)
        if fresh:
            seen = max(event["id"] for event in fresh)
        time.sleep(args.interval)


def _cmd_completion(store: Store | None, args: argparse.Namespace, actor: str) -> int:
    parser = build_parser()
    subs = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    cmds = list(subs.choices)
    if args.shell == "bash":
        print(f'complete -W "{" ".join(cmds)}" lpui')
        print(f'complete -W "{" ".join(cmds)}" lazyplan')
    else:
        print(f"#compdef lpui lazyplan\n_arguments '1:command:({' '.join(cmds)})'")
    return 0


def _post_upgrade_review(json_mode: bool = False) -> None:
    """Refresh setup with the just-installed package; never break the upgrade."""
    argv = [sys.executable, "-m", "lazyplan", "setup", "--post-upgrade"]
    if json_mode:
        argv.append("--json")
    try:
        subprocess.run(
            argv,
            check=False,
            timeout=300,
            stdout=subprocess.DEVNULL if json_mode else None,
        )
    except (OSError, subprocess.SubprocessError):
        return


def _cmd_upgrade(store: Store | None, args: argparse.Namespace, actor: str) -> int:
    """Upgrade this install to the latest release; needs no database."""
    del store, actor
    info = detect()
    installed = package_version()
    try:
        latest = latest_version()
    except UpgradeError as exc:
        # Fail open: a missing network must never break the tool.
        if args.json:
            return _emit(
                args,
                {
                    "method": info.method,
                    "upgradeable": info.upgradeable,
                    "installed": installed,
                    "latest": None,
                    "upgraded": False,
                    "warning": str(exc),
                },
            )
        print(f"warning: {exc}; skipping upgrade check", file=sys.stderr)
        return 0
    payload = {
        "method": info.method,
        "upgradeable": info.upgradeable,
        "installed": installed,
        "latest": latest,
        "upgraded": False,
    }
    if not info.upgradeable and not args.check:
        print(msg_error(UpgradeError(guard_message(info))), file=sys.stderr)
        return 2
    try:
        up_to_date = parse_version(latest) <= parse_version(installed)
    except UpgradeError:
        up_to_date = False
    if args.check or up_to_date:
        if args.json:
            return _emit(args, payload)
        if up_to_date:
            print(f"lpui v{installed} is the latest release ({info.method})")
        else:
            print(f"lpui v{installed} -> v{latest} available ({info.method}); run `lpui upgrade`")
        return 0
    try:
        run_upgrade(info, latest, sys.executable)
    except UpgradeError as exc:
        print(msg_error(exc), file=sys.stderr)
        return 1
    payload["upgraded"] = True
    if not args.json:
        print(f"upgraded lpui v{installed} -> v{latest} ({info.method})")
    _post_upgrade_review(bool(args.json))
    if args.json:
        return _emit(args, payload)
    return 0


def _cmd_help(store: Store, args: argparse.Namespace, actor: str) -> int:
    if args.json:
        return _emit(args, {"help": HELP_TEXT})
    print(HELP_TEXT)
    return 0
