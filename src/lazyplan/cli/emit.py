"""Emit CLI commands."""

from __future__ import annotations

import argparse
import json
import sys

from .. import (
    porcelain,
)
from ..models import Criterion, Milestone, Plan, Status, Task
from ..store import Store


def _emit(args: argparse.Namespace, payload: object) -> int:
    print(json.dumps(payload, indent=2, default=str))
    return 0


def _emit_record(args: argparse.Namespace, line: str, payload: object) -> int:
    """Porcelain prints one record; every other mode keeps the existing emitter."""
    if porcelain.enabled(args):
        print(line)
        return 0
    return _emit(args, payload)


def _emit_read(
    args: argparse.Namespace,
    payload: object,
    porcelain_lines: list[str],
    text: str,
    empty: str = "",
) -> int:
    """Pick JSON, porcelain rows, or human text for one read command."""
    if args.json:
        return _emit(args, payload)
    if porcelain.enabled(args):
        for line in porcelain_lines:
            print(line)
        return 0
    print(text if text else empty)
    return 0


def _progress(store: Store, plan_id: int | None = None, milestone_id: int | None = None) -> str:
    """Task progress for a plan or milestone as `done/total`."""
    if milestone_id is not None:
        tasks = store.list_tasks(milestone_id)
    else:
        tasks = [
            task
            for milestone in store.list_milestones(plan_id or 0)
            for task in store.list_tasks(milestone.id)
        ]
    done = sum(1 for task in tasks if task.status == Status.DONE)
    return f"{done}/{len(tasks)}"


def _porcelain_row(store: Store, obj: Plan | Milestone | Task) -> str:
    """One row for a plan, milestone, or task using its inherited parent id."""
    if isinstance(obj, Plan):
        return porcelain.plan_row(
            obj.id, obj.status.value, obj.name, _progress(store, plan_id=obj.id)
        )
    if isinstance(obj, Milestone):
        return porcelain.milestone_row(
            obj.id,
            obj.status.value,
            obj.title,
            obj.plan_id,
            _progress(store, milestone_id=obj.id),
        )
    return porcelain.task_row(
        obj.id,
        obj.status.value,
        obj.title,
        obj.milestone_id,
        "blocked" if obj.blocked else "-",
    )


def _criterion_row(criteria: Criterion) -> str:
    """One criterion row with its parent kind and id."""
    return porcelain.row(
        "criterion",
        criteria.id,
        "done" if criteria.done else "open",
        criteria.text,
        f"{criteria.parent_kind}:{criteria.parent_id}",
        "-",
    )


def _tty_dot(args: argparse.Namespace) -> str:
    """ANSI dots on a tty; plain for pipes, --json, and porcelain."""
    if getattr(args, "json", False) or porcelain.enabled(args):
        return "plain"
    return "ansi" if sys.stdout.isatty() else "plain"
