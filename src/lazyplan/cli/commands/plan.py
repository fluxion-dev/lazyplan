"""Plan CLI commands."""

from __future__ import annotations

import argparse
import sys

from ... import (
    porcelain,
    services,
)
from ...design import (
    EMPTY_NO_PLANS,
    msg_error,
    msg_not_found,
)
from ...models import Milestone, Plan, Status, Task
from ...render import (
    render_full,
)
from ...store import Store, to_payload
from ..emit import (
    _criterion_row,
    _emit,
    _emit_record,
    _porcelain_row,
)
from ..rows import (
    _list_filters,
    _list_limit,
    _list_lines,
    _list_payload,
    _porcelain_list_lines,
    _porcelain_show_lines,
)


def _resolve_title(args: argparse.Namespace) -> str:
    """--title wins, --name is the legacy alias."""
    if getattr(args, "title", None):
        return str(args.title)
    if getattr(args, "name", None):
        return str(args.name)
    return ""


def _cmd_add_plan(store: Store, args: argparse.Namespace, actor: str) -> int:
    title = _resolve_title(args)
    if not title.strip():
        print("error: plan add needs --title", file=sys.stderr)
        return 2
    desc = args.desc if args.desc is not None else (args.what or "")
    goal = args.goal if args.goal is not None else (args.why or "")
    p = services.create_plan(
        store,
        title,
        desc,
        goal=goal,
        actor=actor,
    )
    return _emit_record(args, _porcelain_row(store, p), {"plan": to_payload(vars(p))})


def _cmd_add_milestone(store: Store, args: argparse.Namespace, actor: str) -> int:
    s = services.create_milestone(
        store,
        args.plan,
        args.title,
        args.desc,
        actor=actor,
    )
    return _emit_record(args, _porcelain_row(store, s), {"milestone": to_payload(vars(s))})


def _cmd_add_task(store: Store, args: argparse.Namespace, actor: str) -> int:
    t = services.create_task(
        store,
        args.milestone,
        args.title,
        description=args.desc,
        actor=actor,
    )
    return _emit_record(args, _porcelain_row(store, t), {"task": to_payload(vars(t))})


def _cmd_update(store: Store, args: argparse.Namespace, actor: str) -> int:
    title_patch = _resolve_title(args) or None
    desc_patch: str | None = args.desc if args.desc is not None else args.what
    updated: Plan | Milestone | Task | None = None
    if args.kind == "plan":
        goal = args.goal if args.goal is not None else args.why
        updated = store.update_plan(
            args.id,
            name=title_patch,
            description=desc_patch,
            goal=goal,
            actor=actor,
        )
    elif args.kind == "milestone":
        updated = store.update_milestone(
            args.id,
            title=title_patch,
            description=desc_patch,
            actor=actor,
        )
    else:
        updated = store.update_task(
            args.id,
            title=title_patch,
            description=desc_patch,
            actor=actor,
        )
    if updated is None:
        print(msg_not_found(args.kind, args.id), file=sys.stderr)
        return 1
    return _emit_record(
        args, _porcelain_row(store, updated), {"updated": to_payload(vars(updated))}
    )


def _cmd_show(store: Store, args: argparse.Namespace, actor: str) -> int:
    full = store.get_full(args.kind, args.id)
    if full is None:
        print(msg_not_found(args.kind, args.id), file=sys.stderr)
        return 1
    if args.json:
        return _emit(args, full)
    if porcelain.enabled(args):
        for line in _porcelain_show_lines(store, args.kind, full):
            print(line)
        return 0
    print(render_full(args.kind, full, files=bool(getattr(args, "files", False))))
    return 0


def _cmd_status(store: Store, args: argparse.Namespace, actor: str) -> int:
    left = store.open_criteria(args.kind, args.id)
    if args.to == "done" and left:
        print(
            f"warning: {len(left)} open acceptance criteria "
            f"({', '.join(c.text[:40] for c in left[:3])}); closing anyway",
            file=sys.stderr,
        )
    ok = services.set_status(store, args.kind, args.id, Status(args.to), actor=actor)
    if not ok:
        print(msg_not_found(args.kind, args.id), file=sys.stderr)
        return 1
    if args.to == "done":
        reason = services.auto_capture_head(store, args.kind, args.id, actor=actor)
        if reason:
            print(
                f"warning: {args.kind} #{args.id} done, but HEAD was not linked: {reason}. "
                f"Commit, then run `lpui link --kind {args.kind} --id {args.id}`.",
                file=sys.stderr,
            )
    payload = {"ok": True, "kind": args.kind, "id": args.id, "to": args.to}
    if porcelain.enabled(args):
        moved = store.get_parent(args.kind, args.id)
        if moved is not None:
            return _emit_record(args, _porcelain_row(store, moved), payload)
    return _emit(args, payload)


def _cmd_delete(store: Store, args: argparse.Namespace, actor: str) -> int:
    before = store.get_parent(args.kind, args.id)
    title = "-"
    parent = "-"
    if isinstance(before, Plan):
        title = before.name
    elif isinstance(before, Milestone):
        title = before.title
        parent = f"plan:{before.plan_id}"
    elif isinstance(before, Task):
        title = before.title
        parent = f"milestone:{before.milestone_id}"
    ok = store.delete(args.kind, args.id, actor=actor)
    if not ok:
        print(msg_not_found(args.kind, args.id), file=sys.stderr)
        return 1
    line = porcelain.row(args.kind, args.id, "deleted", title, parent, "-")
    return _emit_record(args, line, {"ok": True, "deleted": f"{args.kind} #{args.id}"})


def _cmd_reconcile(store: Store, args: argparse.Namespace, actor: str) -> int:
    return _emit(args, {"reconciled": services.reconcile(store, actor=actor)})


def _cmd_add_criteria(store: Store, args: argparse.Namespace, actor: str) -> int:
    c = store.add_criteria(args.kind, args.id, args.text, actor=actor)
    return _emit_record(args, _criterion_row(c), {"criteria": vars(c)})


def _cmd_criteria(store: Store, args: argparse.Namespace, actor: str) -> int:
    found = store.get_parent(args.kind, args.id)
    if found is None:
        print(msg_not_found(args.kind, args.id), file=sys.stderr)
        return 1
    items = store.list_criteria(args.kind, args.id)
    if porcelain.enabled(args):
        for item in items:
            print(_criterion_row(item))
        return 0
    return _emit(args, [vars(c) for c in items])


def _check_uncheck(store: Store, args: argparse.Namespace, actor: str, done: bool) -> int:
    crit = store.set_criteria(args.id, done, actor=actor)
    if crit is None:
        print(msg_not_found("criteria", args.id), file=sys.stderr)
        return 1
    return _emit_record(args, _criterion_row(crit), {"criteria": vars(crit)})


def _cmd_check(store: Store, args: argparse.Namespace, actor: str) -> int:
    return _check_uncheck(store, args, actor, True)


def _cmd_uncheck(store: Store, args: argparse.Namespace, actor: str) -> int:
    return _check_uncheck(store, args, actor, False)


def _cmd_delete_criteria(store: Store, args: argparse.Namespace, actor: str) -> int:
    if not store.delete_criteria(args.id, actor=actor):
        print(msg_not_found("criteria", args.id), file=sys.stderr)
        return 1
    line = porcelain.row("criterion", args.id, "deleted", "-", "-", "-")
    return _emit_record(args, line, {"ok": True, "deleted": f"criteria #{args.id}"})


def _criterion_link(store: Store, args: argparse.Namespace, actor: str, relate: bool) -> int:
    criterion = store.get_criterion(args.id)
    if criterion is None:
        print(msg_not_found("criterion", args.id), file=sys.stderr)
        return 1
    task = store.get_task(args.task)
    if task is None:
        print(msg_not_found("task", args.task), file=sys.stderr)
        return 1
    try:
        if relate:
            store.relate_criterion(args.id, args.task, actor=actor)
        else:
            if not store.unrelate_criterion(args.id, args.task, actor=actor):
                print(
                    msg_error(
                        ValueError(f"criterion #{args.id} is not linked to task #{args.task}")
                    ),
                    file=sys.stderr,
                )
                return 1
    except (KeyError, ValueError) as exc:
        print(msg_error(exc), file=sys.stderr)
        return 1
    payload = {
        "link": {
            "criterion_id": args.id,
            "task_id": args.task,
            "task": task.title,
            "linked": relate,
        }
    }
    if args.json:
        return _emit(args, payload)
    if porcelain.enabled(args):
        print(
            porcelain.link_row(args.id, "linked" if relate else "unlinked", args.task, task.title)
        )
    else:
        verb = "linked" if relate else "unlinked"
        print(f"{verb} criterion #{args.id} {'to' if relate else 'from'} T{args.task} {task.title}")
    return 0


def _cmd_criterion_relate(store: Store, args: argparse.Namespace, actor: str) -> int:
    return _criterion_link(store, args, actor, True)


def _cmd_criterion_unrelate(store: Store, args: argparse.Namespace, actor: str) -> int:
    return _criterion_link(store, args, actor, False)


def _cmd_list(store: Store, args: argparse.Namespace, actor: str) -> int:
    archived, status = _list_filters(args)
    limit = _list_limit(args)
    repo_filter = getattr(args, "repo", None)
    milestone_filter = getattr(args, "milestone", None)
    if args.json:
        return _emit(
            args,
            _list_payload(
                store,
                status,
                archived,
                limit,
                repo_filter,
                milestone_filter,
                args.plan,
            ),
        )
    if porcelain.enabled(args):
        for line in _porcelain_list_lines(
            store,
            status,
            args.plan,
            archived,
            limit,
            repo_filter,
            milestone_filter,
            bool(getattr(args, "tree", False)) or milestone_filter is not None,
        ):
            print(line)
        return 0
    lines = _list_lines(store, args, status, archived, limit, repo_filter, milestone_filter)
    print("\n".join(lines) if lines else EMPTY_NO_PLANS)
    return 0
