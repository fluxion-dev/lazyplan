"""Ui CLI commands."""

from __future__ import annotations

import argparse
import sys

from ... import (
    services,
)
from ...design import (
    EMPTY_NO_PLANS,
)
from ...render import (
    summary_lines,
)
from ...store import Store
from ..emit import (
    _emit,
)
from ..rows import (
    _list_payload,
)


def _interactive_terminal() -> bool:
    """True only when both ends are a terminal; piped runs get the summary."""
    try:
        return sys.stdin.isatty() and sys.stdout.isatty()
    except (AttributeError, ValueError):
        return False


def _plain_overview(store: Store, args: argparse.Namespace) -> int:
    """Non-TTY fallback: a readable summary instead of full-screen ANSI."""
    if getattr(args, "json", False):
        return _emit(
            args,
            _list_payload(store, None, "hide", None, None, None, None),
        )
    print(
        "lpui: no interactive terminal; showing the plan summary (use `lpui list --tree` for detail)",
        file=sys.stderr,
    )
    lines = summary_lines(
        store,
        None,
        None,
        dot="plain",
        archived="hide",
        limit=services.DEFAULT_PLAN_LIMIT,
    )
    print("\n".join(lines) if lines else EMPTY_NO_PLANS)
    return 0


def _cmd_ui(store: Store, args: argparse.Namespace, actor: str) -> int:
    del actor
    if not _interactive_terminal():
        return _plain_overview(store, args)
    from ...tui import run

    return run(db_path=args.db)
