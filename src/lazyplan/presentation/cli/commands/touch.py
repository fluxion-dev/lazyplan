"""Task touch-point CLI commands."""

from __future__ import annotations

import argparse
import sys

from ....store import Store
from ...shared import porcelain
from ...shared.design import msg_error, msg_not_found
from ..emit import _emit_read


def _touch_row(task_id: int, status: str, pattern: str) -> str:
    """One porcelain touch row."""
    return porcelain.row("touch", task_id, status, pattern, f"task:{task_id}", "-")


def _cmd_touch_add(store: Store, args: argparse.Namespace, actor: str) -> int:
    del actor
    task = store.get_task(args.task)
    if task is None:
        print(msg_not_found("task", args.task), file=sys.stderr)
        return 1
    rows = []
    try:
        for path in args.path:
            pattern = store.add_touchpoint(args.task, path)
            rows.append(pattern)
    except ValueError as exc:
        print(msg_error(exc), file=sys.stderr)
        return 2
    return _emit_read(
        args,
        {"task": args.task, "touchpoints": store.list_touchpoints(args.task)},
        [_touch_row(args.task, "added", pattern) for pattern in rows],
        "\n".join(f"T{args.task} {pattern}" for pattern in rows) or "no touch-points",
    )


def _cmd_touch_list(store: Store, args: argparse.Namespace, actor: str) -> int:
    del actor
    if store.get_task(args.task) is None:
        print(msg_not_found("task", args.task), file=sys.stderr)
        return 1
    patterns = store.list_touchpoints(args.task)
    return _emit_read(
        args,
        {"task": args.task, "touchpoints": patterns},
        [_touch_row(args.task, "listed", pattern) for pattern in patterns],
        "\n".join(f"T{args.task} {pattern}" for pattern in patterns) or "no touch-points",
    )


def _cmd_touch_remove(store: Store, args: argparse.Namespace, actor: str) -> int:
    del actor
    if store.get_task(args.task) is None:
        print(msg_not_found("task", args.task), file=sys.stderr)
        return 1
    try:
        removed = store.remove_touchpoint(args.task, args.path)
    except ValueError as exc:
        print(msg_error(exc), file=sys.stderr)
        return 2
    if not removed:
        print(msg_not_found("touch-point", args.path), file=sys.stderr)
        return 1
    return _emit_read(
        args,
        {"task": args.task, "removed": args.path},
        [_touch_row(args.task, "removed", args.path)],
        f"removed {args.path} from T{args.task}",
    )
