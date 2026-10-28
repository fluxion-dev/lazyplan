"""Main CLI commands."""

from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

from .. import (
    porcelain,
    setup,
)
from ..design import (
    msg_error,
)
from ..store import Store
from ..upgrade import (
    cached_latest,
    detect,
    notice_text,
    update_check_enabled,
)
from ..upgrade import (
    latest_version as latest_version,
)
from .commands import (
    _COMMANDS,
    _GROUP_CMDS,
    _cmd_audit,
    _cmd_brief,
    _cmd_completion,
    _cmd_doctor,
    _cmd_hook,
    _cmd_mcp,
    _cmd_setup,
    _cmd_upgrade,
)
from .parser import build_parser, package_version


def _maybe_notice_update(args: argparse.Namespace) -> None:
    """One stderr notice from the shared cache; never touches the network.

    Agent-facing calls (hooks, MCP, porcelain, JSON) stay silent. The TUI
    refreshes the cache in its background update worker.
    """
    if args.cmd in (None, "ui", "upgrade", "hook", "mcp"):
        return
    if getattr(args, "json", False) or getattr(args, "version", False) or porcelain.enabled(args):
        return
    if not update_check_enabled():
        return
    try:
        latest = cached_latest()
        notice = notice_text(detect(), package_version(), latest or "")
    except Exception:
        return
    if notice is not None:
        print(notice, file=sys.stderr)


def _dispatch_storeless(args: argparse.Namespace, actor: str) -> int | None:
    """Commands that must run before a database is opened; None means keep going."""
    handlers = {
        "upgrade": _cmd_upgrade,
        "setup": _cmd_setup,
        "doctor": _cmd_doctor,
        "audit": _cmd_audit,
        "brief": _cmd_brief,
        "mcp": _cmd_mcp,
        "hook": _cmd_hook,
        "completion": _cmd_completion,
    }
    handler = handlers.get(args.cmd)
    return handler(None, args, actor) if handler is not None else None


def _utf8_stdio() -> None:
    """Speak UTF-8 on every pipe; Windows otherwise uses the ANSI code page."""
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper) and stream.encoding.lower() not in (
            "utf-8",
            "utf8",
        ):
            stream.reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    """Dispatch one lpui invocation; exit codes are agent-readable."""
    _utf8_stdio()
    args = build_parser().parse_args(argv)
    noun_group = getattr(args, "noun_group", None)
    if noun_group:
        action = getattr(args, "action", None)
        canonical = _GROUP_CMDS.get((noun_group, action or ""))
        if canonical is None:
            print(f"error: unknown {noun_group} action {action!r}", file=sys.stderr)
            return 2
        args.cmd = canonical
        if noun_group in ("plan", "milestone", "task") and canonical in (
            "update",
            "show",
            "status",
            "delete",
        ):
            args.kind = noun_group
        if noun_group in ("milestone", "task") and canonical == "list":
            args.tree = True
    if getattr(args, "version", False):
        # Before Store(): printing the version must not create a DB.
        print(package_version())
        return 0
    actor = getattr(args, "actor", "human")
    _maybe_notice_update(args)
    if args.cmd is None:
        # Bare `lpui` (or global flags only) opens the standard TUI.
        args.cmd = "ui"
    try:
        setup.ensure(args.cmd, args, Path.cwd(), version=package_version())
    except (OSError, RuntimeError, ValueError) as exc:
        # Setup must never break an agent call; the database still opens.
        print(f"warning: setup skipped: {exc}", file=sys.stderr)
    early = _dispatch_storeless(args, actor)
    if early is not None:
        return early
    # `watch` is `feed --follow`
    if args.cmd == "watch":
        args.cmd = "feed"
        args.follow = True
        args.interval = 1.0
        args.json = getattr(args, "json", False)
    try:
        store = Store(args.db)
    except RuntimeError as exc:
        print(msg_error(exc), file=sys.stderr)
        return 2
    try:
        handler = _COMMANDS.get(args.cmd)
        if handler is None:
            raise AssertionError(args.cmd)
        return handler(store, args, actor)
    except (ValueError, KeyError) as exc:
        print(msg_error(exc), file=sys.stderr)
        return 2
