"""Agent registry CLI: start, end, show, list, sweep, and archive rows."""

from __future__ import annotations

import argparse
import os
import sys
import time

from ....core.entities import Agent
from ....core.policies.agents import normalize_role, parse_agent_id, parse_pid
from ....core.ports.app import AppPort
from ....core.serialization import to_payload
from ...shared import porcelain
from ...shared.design import msg_error, msg_not_found
from ...shared.session_labels import plan_names
from ..emit import _emit_read, _emit_record
from ..store import optional_store as _optional_store


def agent_row(agent: Agent) -> str:
    """One porcelain agent row; extra is the exact worktree or unbound reason."""
    plan = f"plan:{agent.plan_id}" if agent.plan_id is not None else "-"
    extra = agent.worktree or agent.unbound_reason or "-"
    return porcelain.row("agent", agent.id, agent.status, agent.agent, plan, extra)


def _duration_text(seconds: float) -> str:
    """Short duration: 42s, 12m, 2.1h, or 3.4d."""
    if seconds < 60:
        return f"{max(0, round(seconds))}s"
    if seconds < 3600:
        return f"{max(1, round(seconds / 60))}m"
    if seconds < 86400:
        return f"{seconds / 3600:.1f}h"
    return f"{seconds / 86400:.1f}d"


def agent_text(agent: Agent, now: float | None = None, plan_title: str = "") -> str:
    """One human agent line, then the exact identity and binding fields."""
    stamp = time.time() if now is None else now
    plan = f"P{agent.plan_id}" if agent.plan_id is not None else "no plan"
    if plan_title:
        plan = f"{plan} {plan_title}"
    if agent.task_id is not None:
        plan += f" T{agent.task_id}"
    branch = f" on {agent.branch}" if agent.branch else ""
    host = f" via {agent.host}" if agent.host and agent.host != "unknown" else ""
    if agent.host_session:
        short = agent.host_session[-6:]
        host = f"{host} · {short}" if host else f" via {short}"
    head = f" [{agent.head_sha[:8]}]" if agent.head_sha else ""
    lines = [
        f"A{agent.id} [{agent.status}] @{agent.agent}{host} {plan}{branch}{head} "
        f"({_duration_text(agent.duration(stamp))})"
    ]
    identity = [
        f"role {agent.role}",
        f"model {agent.model}",
        f"pid {agent.pid or '-'}",
        f"parent {f'A{agent.parent_id}' if agent.parent_id else '-'}",
    ]
    lines.append("  " + " · ".join(identity))
    context = [
        f"worktree {agent.worktree or '-'}",
        f"repo {agent.repo_path or '-'}",
        f"head {agent.head_sha or '-'}",
    ]
    lines.append("  " + " · ".join(context))
    if agent.unbound:
        lines.append(f"  unbound  {agent.unbound_reason or 'no exact plan'}")
    if agent.summary:
        lines.append(f"  summary  {agent.summary}")
    if agent.handoff:
        lines.append(f"  handoff  {agent.handoff}")
    return "\n".join(lines)


def agent_payload(store: AppPort, agent: Agent) -> dict:
    """JSON-safe agent fields plus the resolved plan and task titles."""
    payload = to_payload(vars(agent))
    plan = store.get_plan(agent.plan_id) if agent.plan_id is not None else None
    task = store.get_task(agent.task_id) if agent.task_id is not None else None
    payload["plan_title"] = plan.name if plan is not None else ""
    payload["task_title"] = task.title if task is not None else ""
    payload["unbound"] = agent.unbound
    return payload


def _cmd_agent_start(store: AppPort, args: argparse.Namespace, actor: str) -> int:
    from lazyplan import services

    if args.force and not str(args.reason).strip():
        print(msg_error(ValueError("--force needs --reason")), file=sys.stderr)
        return 2
    try:
        agent = services.start_agent(
            store,
            actor,
            host=args.host or "manual",
            host_session=args.session,
            agent=args.agent or actor,
            role=normalize_role(args.role),
            model=args.model or "unknown",
            pid=parse_pid(args.pid),
            cwd=os.getcwd(),
            plan_id=args.plan,
            task_id=args.task,
            force=bool(args.force),
            reason=args.reason,
            note=args.note,
        )
    except services.AgentStartError as exc:
        print(msg_error(exc), file=sys.stderr)
        return 2
    except KeyError as exc:
        print(msg_error(exc), file=sys.stderr)
        return 1
    except (ValueError, OSError) as exc:
        print(msg_error(exc), file=sys.stderr)
        return 2
    payload = {"agent": agent_payload(store, agent)}
    return _emit_record(args, agent_row(agent), payload)


def _cmd_agent_end(store: AppPort, args: argparse.Namespace, actor: str) -> int:
    from lazyplan import services

    target = args.id
    if target is None:
        current = services.current_agent(store, actor)
        target = current.id if current is not None else None
    if target is None:
        print("error: no live agent; pass --id", file=sys.stderr)
        return 1
    existing = store.get_agent(target)
    if existing is None:
        print(msg_not_found("agent", target), file=sys.stderr)
        return 1
    try:
        ended = services.end_agent(store, target, actor, summary=args.summary, handoff=args.handoff)
    except KeyError as exc:
        print(msg_error(exc), file=sys.stderr)
        return 1
    except ValueError as exc:
        print(msg_error(exc), file=sys.stderr)
        return 2
    return _emit_record(args, agent_row(ended), {"agent": agent_payload(store, ended)})


def _resolve_show(store: AppPort, raw: str) -> tuple[Agent | None, int | None]:
    """Show a live agent by A id, or a history row by S id."""
    try:
        agent_id = parse_agent_id(raw)
    except ValueError:
        agent_id = 0
    if agent_id:
        agent = store.get_agent(agent_id)
        if agent is not None:
            return agent, None
    from ....core.policies.sessions import parse_session_id

    try:
        session_id = parse_session_id(raw)
    except ValueError:
        return None, None
    return None, session_id


def _cmd_agent_show(store: AppPort | None, args: argparse.Namespace, actor: str) -> int:
    from lazyplan import services

    try:
        db = store or _optional_store(args)
    except (RuntimeError, OSError) as exc:
        print(msg_error(exc), file=sys.stderr)
        return 2
    if db is None:
        return _emit_read(args, {"agent": None, "events": [], "counts": {}}, [], "no agents")
    store = db
    if args.id is None:
        current = services.current_agent(store, actor)
        if current is None:
            return _emit_read(
                args, {"agent": None, "events": [], "counts": {}}, [], "no live agent"
            )
        agent_id = current.id
    else:
        agent, session_id = _resolve_show(store, args.id)
        if agent is None and session_id is not None:
            return _show_history(store, args, session_id)
        if agent is None:
            print(msg_not_found("agent", args.id), file=sys.stderr)
            return 1
        agent_id = agent.id
    result = services.show_agent(store, agent_id, limit=args.limit)
    if result is None:
        print(msg_not_found("agent", agent_id), file=sys.stderr)
        return 1
    agent = result["agent"]
    counts = ", ".join(f"{action} {count}" for action, count in result["counts"].items()) or "-"
    titles = plan_names(store)
    lines = [
        agent_text(agent, plan_title=titles.get(agent.plan_id or 0, "")),
        f"  events   {counts}",
    ]
    for event in result["events"]:
        lines.append(
            f"  #{event.id} {event.event}: {event.from_status} -> {event.to_status}"
            f" {event.detail}".rstrip()
        )
    payload = {
        "agent": agent_payload(store, agent),
        "counts": result["counts"],
        "events": [to_payload(vars(event)) for event in result["events"]],
    }
    return _emit_read(args, payload, [agent_row(agent)], "\n".join(lines))


def _show_history(store: AppPort, args: argparse.Namespace, session_id: int) -> int:
    session = store.get_session(session_id)
    if session is None:
        print(msg_not_found("session", session_id), file=sys.stderr)
        return 1
    events = store.events_for_session(session_id, limit=args.limit)
    counts = store.session_counts(session_id)
    titles = plan_names(store)
    label = f"P{session.plan_id}" if session.plan_id is not None else "no plan"
    title = titles.get(session.plan_id or 0, "")
    lines = [
        f"S{session.id} [{'ended' if session.ended else 'open'}] @{session.actor}"
        f" {label}{' ' + title if title else ''}",
        f"  summary  {session.summary or '-'}",
        f"  handoff  {session.handoff or '-'}",
    ]
    payload = {
        "session": to_payload(vars(session)),
        "counts": counts,
        "events": events,
        "history": True,
    }
    return _emit_read(
        args,
        payload,
        [
            porcelain.row(
                "session",
                session.id,
                "history",
                session.actor,
                f"plan:{session.plan_id}" if session.plan_id else "-",
                "-",
            )
        ],
        "\n".join(lines),
    )


def _cmd_agent_list(store: AppPort | None, args: argparse.Namespace, actor: str) -> int:

    del actor
    try:
        db = store or _optional_store(args)
    except (RuntimeError, OSError) as exc:
        print(msg_error(exc), file=sys.stderr)
        return 2
    if db is None:
        return _emit_read(args, [], [], "no agents")
    rows = db.list_agents(
        plan_id=args.plan,
        open_only=bool(getattr(args, "open", False)),
        live_only=bool(getattr(args, "live", False)),
        host=getattr(args, "host", ""),
        status=getattr(args, "status", ""),
        limit=args.limit,
    )
    titles = plan_names(db)
    return _emit_read(
        args,
        [agent_payload(db, row) for row in rows],
        [agent_row(row) for row in rows],
        "\n".join(agent_text(row, plan_title=titles.get(row.plan_id or 0, "")) for row in rows),
    )


def _cmd_agent_sweep(store: AppPort, args: argparse.Namespace, actor: str) -> int:
    from lazyplan import services

    del actor
    lost = services.sweep_lost(store)
    titles = plan_names(store)
    return _emit_read(
        args,
        [agent_payload(store, row) for row in lost],
        [agent_row(row) for row in lost],
        "\n".join(agent_text(row, plan_title=titles.get(row.plan_id or 0, "")) for row in lost)
        or "no lost agents",
    )


def _cmd_agent_archive(store: AppPort, args: argparse.Namespace, actor: str) -> int:
    ids = list(getattr(args, "id", []) or [])
    count = store.archive_agents(ids, actor=actor)
    return _emit_read(
        args,
        {"archived": count},
        [porcelain.row("agent", "archive", "archived", count, "-", "-")],
        f"archived {count} agent(s)",
    )


def _cmd_agent_restore(store: AppPort, args: argparse.Namespace, actor: str) -> int:
    if not store.restore_agent(args.id, actor=actor):
        print(msg_error(ValueError(f"agent A{args.id} is not archived")), file=sys.stderr)
        return 1
    return _emit_read(
        args,
        {"restored": args.id},
        [porcelain.row("agent", args.id, "restored", "-", "-", "-")],
        f"restored A{args.id}",
    )


def _cmd_agent_history(store: AppPort | None, args: argparse.Namespace, actor: str) -> int:
    del actor
    try:
        db = store or _optional_store(args)
    except (RuntimeError, OSError) as exc:
        print(msg_error(exc), file=sys.stderr)
        return 2
    if db is None:
        return _emit_read(args, [], [], "no sessions")
    rows = db.list_sessions(plan_id=args.plan, limit=args.limit)
    titles = plan_names(db)
    payload = [to_payload(vars(row)) for row in rows]
    lines = []
    for row in rows:
        plan = "no plan"
        if row.plan_id is not None:
            plan = f"P{row.plan_id} {titles.get(row.plan_id, '')}".strip()
        state = "ended" if row.ended else "open"
        lines.append(f"S{row.id} [{state}] @{row.actor} {plan}")
    porcelain_rows = [
        porcelain.row(
            "session",
            row.id,
            "history",
            row.actor,
            f"plan:{row.plan_id}" if row.plan_id else "-",
            "-",
        )
        for row in rows
    ]
    return _emit_read(args, payload, porcelain_rows, "\n".join(lines) or "no sessions")


def _cmd_session_start(store: AppPort, args: argparse.Namespace, actor: str) -> int:
    """Hidden alias: one managed agent start, serialized as a session."""
    from lazyplan import services

    if args.force and not str(args.reason).strip():
        print(msg_error(ValueError("--force needs --reason")), file=sys.stderr)
        return 2
    try:
        agent = services.start_agent(
            store,
            actor,
            host=args.host or "manual",
            host_session=args.session,
            agent=args.agent or actor,
            role=normalize_role(args.role),
            model=args.model or "unknown",
            pid=parse_pid(args.pid),
            cwd=os.getcwd(),
            plan_id=args.plan,
            task_id=args.task,
            force=bool(args.force),
            reason=args.reason,
            note=args.note,
        )
    except services.AgentStartError as exc:
        print(msg_error(exc), file=sys.stderr)
        return 2
    except KeyError as exc:
        print(msg_error(exc), file=sys.stderr)
        return 1
    except (ValueError, OSError) as exc:
        print(msg_error(exc), file=sys.stderr)
        return 2
    return _emit_record(
        args,
        agent_row(agent),
        {"session": agent_payload(store, agent), "agent": agent_payload(store, agent)},
    )


def _cmd_session_end(store: AppPort, args: argparse.Namespace, actor: str) -> int:
    """Hidden alias: end one agent, serialized as a session."""
    from lazyplan import services

    target = args.id
    if target is None:
        current = services.current_agent(store, actor)
        target = current.id if current is not None else None
    if target is None:
        print("error: no active agent; pass --id", file=sys.stderr)
        return 1
    existing = store.get_agent(target)
    if existing is None:
        print(msg_not_found("session", target), file=sys.stderr)
        return 1
    try:
        ended = services.end_agent(store, target, actor, summary=args.summary, handoff=args.handoff)
    except (KeyError, ValueError) as exc:
        print(msg_error(exc), file=sys.stderr)
        return 2
    return _emit_record(
        args,
        agent_row(ended),
        {"session": agent_payload(store, ended), "agent": agent_payload(store, ended)},
    )


def _cmd_session_show(store: AppPort | None, args: argparse.Namespace, actor: str) -> int:
    """Hidden alias: show a live agent or one legacy history row."""
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
        current = services.current_agent(db, actor)
        if current is None:
            return _emit_read(
                args, {"session": None, "events": [], "counts": {}}, [], "no active agent"
            )
        return _show_agent_as_session(db, args, current.id)
    agent, session_id = _resolve_show(db, target)
    if agent is not None:
        return _show_agent_as_session(db, args, agent.id)
    if session_id is None:
        print(msg_not_found("session", target), file=sys.stderr)
        return 1
    return _show_history(db, args, session_id)


def _show_agent_as_session(store: AppPort, args: argparse.Namespace, agent_id: int) -> int:
    from lazyplan import services

    result = services.show_agent(store, agent_id, limit=args.limit)
    if result is None:
        print(msg_not_found("agent", agent_id), file=sys.stderr)
        return 1
    agent = result["agent"]
    titles = plan_names(store)
    lines = [agent_text(agent, plan_title=titles.get(agent.plan_id or 0, ""))]
    payload = {
        "session": agent_payload(store, agent),
        "agent": agent_payload(store, agent),
        "counts": result["counts"],
        "events": [to_payload(vars(event)) for event in result["events"]],
    }
    return _emit_read(args, payload, [agent_row(agent)], "\n".join(lines))


def _cmd_session_list(store: AppPort | None, args: argparse.Namespace, actor: str) -> int:
    """Hidden alias: list live agents, or history with --history."""
    if getattr(args, "history", False):
        return _cmd_agent_history(store, args, actor)
    if getattr(args, "all", False):
        args.live = False
        args.open = True
    if not hasattr(args, "live"):
        args.live = False
    if not hasattr(args, "open"):
        args.open = False
    return _cmd_agent_list(store, args, actor)
