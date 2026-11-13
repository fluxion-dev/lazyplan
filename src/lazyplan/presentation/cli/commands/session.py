"""Session CLI commands."""

from __future__ import annotations

import argparse
import sys
import time

from lazyplan.services.worktrees import checkout_gate

from ....core.entities import Session
from ....core.ports.app import AppPort
from ....core.ports.sessions import SessionsPort
from ....core.serialization import to_payload
from ...shared import porcelain
from ...shared.design import msg_error, msg_not_found
from ...shared.session_labels import plan_label, plan_names, task_label
from ..emit import _emit_read, _emit_record
from ..store import optional_store as _optional_store
from .worktree import record_worktree_override


def _session_row(session: Session) -> str:
    """One porcelain session row; extra is the live phase."""
    from lazyplan import services

    status = "ended" if session.ended else "open"
    plan = f"plan:{session.plan_id}" if session.plan_id is not None else "-"
    phase = services.session_state(session)
    return porcelain.row("session", session.id, status, session.actor, plan, phase)


def _duration_text(seconds: float) -> str:
    """Short duration: 12m, 2.1h, or 3.4d."""
    if seconds < 3600:
        return f"{max(1, round(seconds / 60))}m"
    if seconds < 86400:
        return f"{seconds / 3600:.1f}h"
    return f"{seconds / 86400:.1f}d"


def _session_text(session: Session, now: float | None = None, plan_title: str = "") -> str:
    """One human session line."""
    from lazyplan import services

    stamp = time.time() if now is None else now
    state = services.session_state(session, stamp)
    plan = plan_label(session, plan_title, empty="-")
    task = task_label(session)
    label = f" {plan} {task}" if task else f" {plan}"
    branch = f" on {session.branch}" if session.branch else ""
    host = f" via {session.host}" if session.host and session.host != session.actor else ""
    if session.host_session:
        short = session.host_session[-4:]
        host = f"{host} · {short}" if host else f" via {short}"
    line = (
        f"S{session.id} [{state}] {session.actor}{host}{label}{branch} "
        f"({_duration_text(session.duration(stamp))})"
    )
    if session.summary:
        line += f"\n  summary  {session.summary}"
    if session.handoff:
        line += f"\n  handoff  {session.handoff}"
    return line


def _session_payload(session: Session) -> dict:
    """JSON-safe session fields."""
    return to_payload(vars(session))


def _cmd_session_start(store: AppPort, args: argparse.Namespace, actor: str) -> int:
    from lazyplan import services

    repo = store.checkout_path()
    branch = args.branch.strip() or services.attribution.current_branch(repo)
    explicit = args.plan is not None
    plan_id = args.plan
    if plan_id is None:
        plan_id = services.attribution.resolve(store, repo, branch).plan_id
    if explicit and plan_id is not None:
        blocker = checkout_gate(store, plan_id, repo)
        if blocker:
            if not args.force:
                print(msg_error(ValueError(blocker)), file=sys.stderr)
                return 2
            if not str(getattr(args, "reason", "") or "").strip():
                print(msg_error(ValueError("--force needs --reason")), file=sys.stderr)
                return 2
            record_worktree_override(store, plan_id, actor, str(getattr(args, "reason", "")))
    try:
        result = services.start_session(
            store,
            actor,
            plan_id=plan_id,
            branch=branch,
            note=args.note,
            force=bool(args.force),
            plan_source="manual" if explicit else "auto",
        )
    except KeyError as exc:
        print(msg_error(exc), file=sys.stderr)
        return 1
    except (ValueError, OSError) as exc:
        print(msg_error(exc), file=sys.stderr)
        return 2
    session = result["session"]
    payload = {
        "session": _session_payload(session),
        "previous": _session_payload(result["previous"]) if result["previous"] else None,
    }
    return _emit_record(args, _session_row(session), payload)


def _cmd_session_end(store: SessionsPort, args: argparse.Namespace, actor: str) -> int:
    from lazyplan import services

    session = services.current_session(store, actor) if args.id is None else None
    target = session.id if session is not None else args.id
    if target is None:
        print("error: no active session; pass --id", file=sys.stderr)
        return 1
    existing = store.get_session(target)
    if existing is not None and existing.ended:
        print(f"error: session S{target} has already ended", file=sys.stderr)
        return 1
    try:
        ended = services.end_session(
            store, target, actor, summary=args.summary, handoff=args.handoff
        )
    except KeyError as exc:
        print(msg_error(exc), file=sys.stderr)
        return 1
    except ValueError as exc:
        print(msg_error(exc), file=sys.stderr)
        return 2
    return _emit_record(args, _session_row(ended), {"session": _session_payload(ended)})


def _cmd_session_show(store: AppPort | None, args: argparse.Namespace, actor: str) -> int:
    from lazyplan import services

    try:
        db = store or _optional_store(args)
    except (RuntimeError, OSError) as exc:
        print(msg_error(exc), file=sys.stderr)
        return 2
    if db is None:
        return _emit_read(args, {"session": None, "events": [], "counts": {}}, [], "no sessions")
    target = args.id
    if target is None:
        current = services.current_session(db, actor)
        target = current.id if current is not None else None
    if target is None:
        return _emit_read(
            args, {"session": None, "events": [], "counts": {}}, [], "no active session"
        )
    result = services.show_session(db, target, limit=args.limit)
    if result is None:
        print(msg_not_found("session", target), file=sys.stderr)
        return 1
    session = result["session"]
    titles = plan_names(db)
    counts = ", ".join(f"{action} {count}" for action, count in result["counts"].items()) or "-"
    lines = [
        _session_text(session, plan_title=titles.get(session.plan_id or 0, "")),
        f"  events   {counts}",
    ]
    for event in result["events"]:
        lines.append(f"  #{event['id']} {event['kind']}/{event['action']}: {event['detail']}")
    payload = {
        "session": _session_payload(session),
        "counts": result["counts"],
        "events": result["events"],
    }
    return _emit_read(args, payload, [_session_row(session)], "\n".join(lines))


def _cmd_session_list(store: AppPort | None, args: argparse.Namespace, actor: str) -> int:
    from lazyplan import services

    try:
        db = store or _optional_store(args)
    except (RuntimeError, OSError) as exc:
        print(msg_error(exc), file=sys.stderr)
        return 2
    if db is None:
        return _emit_read(args, [], [], "no sessions")
    rows = services.list_sessions(
        db,
        actor="" if args.all else actor,
        plan_id=args.plan,
        open_only=bool(args.open),
        limit=args.limit,
    )
    titles = plan_names(db)
    return _emit_read(
        args,
        [_session_payload(row) for row in rows],
        [_session_row(row) for row in rows],
        "\n".join(_session_text(row, plan_title=titles.get(row.plan_id or 0, "")) for row in rows)
        or "no sessions",
    )
