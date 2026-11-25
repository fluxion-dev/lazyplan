"""Task brief CLI: the fresh-session starting context and its budget."""

from __future__ import annotations

import argparse
import sys

from lazyplan.core.policies.context import DEFAULT_CONTEXT_WINDOW
from lazyplan.core.ports.insights import InsightsPort
from lazyplan.infrastructure.profiles import context_windows
from lazyplan.services import task_brief

from ...shared import porcelain
from ...shared.design import msg_error, msg_not_found
from ..emit import _emit


def _cmd_task_brief(store: InsightsPort, args: argparse.Namespace, actor: str) -> int:
    """Print one task's fresh-session brief and enforce its budget."""
    del actor
    task = store.get_task(args.id)
    if task is None:
        print(msg_not_found("task", args.id), file=sys.stderr)
        return 1
    windows = context_windows(store.db_path, host=args.host)
    window = args.context_window or windows.get(task.role, DEFAULT_CONTEXT_WINDOW)
    try:
        brief = task_brief.build(store, task.id, window, args.percent)
    except (KeyError, ValueError) as exc:
        print(msg_error(exc), file=sys.stderr)
        return 2
    if args.json:
        _emit(args, brief.to_dict())
    elif porcelain.enabled(args):
        print(
            porcelain.row(
                "brief",
                brief.task_id,
                "ok" if brief.fits else "over",
                f"{brief.tokens}/{brief.budget} tokens",
                f"task:{brief.task_id}",
                f"{brief.percent}% of {brief.window}",
            )
        )
    else:
        print(brief.text, end="")
    if brief.fits:
        return 0
    try:
        brief.require_fits()
    except task_brief.ContextBudgetError as exc:
        print(msg_error(exc), file=sys.stderr)
    return 2
