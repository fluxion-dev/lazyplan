"""Agent registry use cases: managed starts, events, liveness, and ends."""

from __future__ import annotations

import time
from pathlib import Path

from ..core.entities import Agent
from ..core.policies.agents import normalize_status, status_for_event
from ..core.ports.agents import AgentsPort, AgentsReadPort
from ..core.ports.app import AppPort
from ..infrastructure.process import process_alive, process_start
from .agent_identity import AgentIdentity, GitFacts, git_facts, resolve_binding


class AgentStartError(ValueError):
    """A managed start that cannot prove an exact plan or worktree."""

    def __init__(self, message: str, reason: str = "", path: str = "") -> None:
        super().__init__(message)
        self.reason = reason or "unbound"
        self.path = path


def start_agent(
    store: AppPort,
    actor: str,
    *,
    host: str = "unknown",
    host_session: str = "",
    agent: str = "unknown",
    role: str = "primary",
    model: str = "unknown",
    parent_id: int | None = None,
    pid: int = 0,
    cwd: str = "",
    plan_id: int | None = None,
    task_id: int | None = None,
    managed: bool = True,
    force: bool = False,
    reason: str = "",
    note: str = "",
    now: float | None = None,
) -> Agent:
    """Register one agent, refusing a managed start without an exact plan."""
    stamp = time.time() if now is None else now
    facts = git_facts(cwd or None)
    existing = _open_for_host(store, host, host_session) if host_session else None
    plan, task, unbound = _start_target(
        store, facts, cwd, plan_id, managed=managed, force=force, reason=reason
    )
    identity = _identity(host, host_session, agent, role, model, pid, cwd)
    if existing is not None:
        return _refresh_existing(store, existing, identity, facts, plan, task, unbound, note, stamp)
    return _add_started(
        store,
        actor,
        identity,
        facts,
        plan,
        task,
        unbound,
        parent_id,
        note,
        stamp,
    )


def _identity(
    host: str,
    host_session: str,
    agent: str,
    role: str,
    model: str,
    pid: int,
    cwd: str,
) -> AgentIdentity:
    """Build the normalized identity for a start or refresh."""
    return AgentIdentity(
        host=host,
        host_session=host_session,
        agent=agent,
        role=role,
        model=model,
        pid=pid,
        process_start=process_start(pid) if pid else "",
        cwd=cwd,
    )


def _start_target(
    store: AppPort,
    facts: GitFacts,
    cwd: str,
    plan_id: int | None,
    *,
    managed: bool,
    force: bool,
    reason: str,
) -> tuple[int | None, int | None, str]:
    """Prove the plan and task for a managed start, or refuse with a reason."""
    binding = resolve_binding(store, facts.worktree or cwd, facts.repo_path, plan_id)
    override = force and bool(reason.strip())
    if managed and binding.plan_id is None and not override:
        raise AgentStartError(
            binding.reason or "no exact plan", reason="unbound", path=facts.worktree
        )
    if plan_id is not None and binding.plan_id != plan_id and not override:
        raise AgentStartError(binding.reason, reason="worktree_mismatch", path=facts.worktree)
    plan = plan_id if plan_id is not None else binding.plan_id
    task = None if plan is None else binding.task_id
    unbound = "" if plan is not None else binding.reason
    if override and binding.plan_id is None:
        unbound = f"override: {reason.strip()[:200]}"
    return plan, task, unbound


def _add_started(
    store: AppPort,
    actor: str,
    identity: AgentIdentity,
    facts: GitFacts,
    plan: int | None,
    task: int | None,
    unbound: str,
    parent_id: int | None,
    note: str,
    stamp: float,
) -> Agent:
    """Insert the first row for a new agent."""
    return store.add_agent(
        actor,
        host=identity.host,
        host_session=identity.host_session,
        agent=identity.agent,
        role=identity.role,
        model=identity.model,
        parent_id=parent_id,
        pid=identity.pid,
        process_start=identity.process_start,
        repo_path=facts.repo_path,
        worktree=facts.worktree,
        branch=facts.branch,
        head_sha=facts.head_sha,
        plan_id=plan,
        task_id=task,
        unbound_reason=unbound,
        note=note,
        now=stamp,
    )


def _open_for_host(store: AppPort, host: str, host_session: str) -> Agent | None:
    """Newest open row for one exact host session, if any."""
    rows = store.agents_for_host(host, host_session, open_only=True)
    return rows[-1] if rows else None


def _refresh_existing(
    store: AppPort,
    agent: Agent,
    identity: AgentIdentity,
    facts: GitFacts,
    plan_id: int | None,
    task_id: int | None,
    unbound: str,
    note: str,
    stamp: float,
) -> Agent:
    """Update an existing row with refreshed exact facts before the transition."""
    fields: dict[str, object] = {
        "host": identity.host,
        "host_session": identity.host_session,
        "agent": identity.agent,
        "role": identity.role,
        "model": identity.model,
        "pid": identity.pid,
        "process_start": identity.process_start,
        "repo_path": facts.repo_path,
        "worktree": facts.worktree,
        "branch": facts.branch,
        "head_sha": facts.head_sha,
        "plan_id": plan_id,
        "task_id": task_id,
        "unbound_reason": unbound,
    }
    updated = store.patch_agent(agent.id, now=stamp, **fields)
    if note:
        store.transition_agent(agent.id, updated.status, event="note", detail=note, now=stamp)
    return updated


def find_agent(
    store: AppPort,
    host: str = "",
    host_session: str = "",
    pid: int = 0,
    cwd: str = "",
) -> Agent | None:
    """Resolve one open agent by exact host session, PID, then checkout."""
    if host_session:
        rows = store.agents_for_host(host or "unknown", host_session, open_only=True)
        return rows[-1] if rows else None
    if pid:
        for row in store.list_agents(open_only=True, limit=200):
            if row.pid == pid and process_alive(row.pid, row.process_start) is not False:
                return row
    if cwd:
        worktree = git_facts(cwd).worktree or str(Path(cwd).expanduser().resolve())
        if worktree:
            wanted = store.normalize_repo_path(worktree)
            for row in store.list_agents(live_only=True, limit=200):
                if wanted in (
                    store.normalize_repo_path(row.worktree),
                    store.normalize_repo_path(row.repo_path),
                ):
                    return row
    return None


def apply_event(
    store: AppPort,
    actor: str,
    event: str,
    identity: AgentIdentity,
    *,
    plan_id: int | None = None,
    force: bool = False,
    reason: str = "",
    summary: str = "",
    handoff: str = "",
    now: float | None = None,
) -> Agent | None:
    """Apply one host lifecycle event to the exact agent row."""
    stamp = time.time() if now is None else now
    status = status_for_event(event)
    existing = find_agent(store, identity.host, identity.host_session, identity.pid, identity.cwd)
    if existing is None:
        if event == "session-end" or event in ("pre-tool", "post-tool", "pre-compact"):
            return None
        agent = _register_host_agent(
            store,
            actor,
            identity,
            plan_id=plan_id,
            force=force,
            reason=reason,
            now=stamp,
        )
        if status == "starting":
            return agent
        return store.transition_agent(
            agent.id,
            status,
            event=event,
            detail=identity.host_session or identity.host,
            now=stamp,
        )
    if event == "session-end":
        return store.end_agent(
            existing.id,
            actor,
            summary=summary or f"ended by {identity.host}",
            handoff=handoff,
            now=stamp,
        )
    facts = git_facts(identity.cwd or None)
    refreshed = _refresh_existing(
        store,
        existing,
        identity,
        facts,
        existing.plan_id if plan_id is None else plan_id,
        existing.task_id,
        existing.unbound_reason,
        "",
        stamp,
    )
    if status == refreshed.status:
        return store.transition_agent(
            existing.id,
            status,
            event=event,
            detail=identity.host_session or identity.host,
            now=stamp,
        )
    return store.transition_agent(
        refreshed.id,
        status,
        event=event,
        detail=identity.host_session or identity.host,
        now=stamp,
    )


def _register_host_agent(
    store: AppPort,
    actor: str,
    identity: AgentIdentity,
    *,
    plan_id: int | None,
    force: bool,
    reason: str,
    now: float,
) -> Agent:
    """Register a host row; unbound rows keep the exact refusal reason."""
    facts = git_facts(identity.cwd or None)
    binding = resolve_binding(store, facts.worktree or identity.cwd, facts.repo_path, plan_id)
    parent_id = _parent_agent(store, identity)
    unbound = "" if binding.plan_id is not None else binding.reason
    if force and reason.strip() and binding.plan_id is None:
        unbound = f"override: {reason.strip()[:200]}"
    return store.add_agent(
        actor,
        host=identity.host,
        host_session=identity.host_session,
        agent=identity.agent,
        role=identity.role,
        model=identity.model,
        parent_id=parent_id,
        pid=identity.pid,
        process_start=identity.process_start,
        repo_path=facts.repo_path,
        worktree=facts.worktree,
        branch=facts.branch,
        head_sha=facts.head_sha,
        plan_id=binding.plan_id if plan_id is None else plan_id,
        task_id=binding.task_id,
        unbound_reason=unbound,
        note=identity.parent_session,
        now=now,
    )


def _parent_agent(store: AppPort, identity: AgentIdentity) -> int | None:
    """Parent row for a child subagent, by exact host session."""
    if identity.role != "subagent" or not identity.parent_session:
        return None
    parent = _open_for_host(store, identity.host, identity.parent_session)
    return None if parent is None else parent.id


def end_agent(
    store: AppPort,
    agent_id: int,
    actor: str,
    summary: str = "",
    handoff: str = "",
    now: float | None = None,
) -> Agent:
    """End one agent and close every live child pointing at it."""
    return store.end_agent(agent_id, actor, summary=summary, handoff=handoff, now=now)


def sweep_lost(store: AgentsPort, now: float | None = None) -> list[Agent]:
    """Mark rows whose process is gone as lost; never closes on time."""
    stamp = time.time() if now is None else now
    lost: list[Agent] = []
    for row in store.open_agents_with_pids():
        if process_alive(row.pid, row.process_start) is not False:
            continue
        try:
            lost.append(
                store.transition_agent(
                    row.id,
                    "lost",
                    event="lost",
                    detail=f"process {row.pid} is gone",
                    now=stamp,
                )
            )
        except (KeyError, ValueError):
            continue
    return lost


def agent_state(agent: Agent) -> str:
    """The explicit status word the tracker paints."""
    return normalize_status(agent.status)


def show_agent(store: AgentsReadPort, agent_id: int, limit: int = 50) -> dict | None:
    """One agent with its transitions and event counts."""
    agent = store.get_agent(agent_id)
    if agent is None:
        return None
    return {
        "agent": agent,
        "events": store.agent_events(agent_id, limit=limit),
        "counts": store.agent_event_counts(agent_id),
    }


def previous_agent(
    store: AgentsReadPort,
    plan_id: int | None = None,
    repo_path: str = "",
) -> dict | None:
    """Most recently ended agent as a compact resume block."""
    row = store.latest_ended_agent(plan_id=plan_id, repo_path=repo_path)
    if row is not None:
        return {
            "id": row.id,
            "label": f"A{row.id}",
            "agent": row.agent,
            "ended_at": row.ended_at,
            "summary": row.summary,
            "handoff": row.handoff,
        }
    legacy = store.latest_ended_session(plan_id=plan_id, repo_path=repo_path)
    if legacy is None:
        return None
    return {
        "id": legacy.id,
        "label": f"S{legacy.id}",
        "agent": legacy.actor,
        "ended_at": legacy.ended_at,
        "summary": legacy.summary,
        "handoff": legacy.handoff,
    }


def current_agent(store: AgentsReadPort, actor: str = "") -> Agent | None:
    """The open agent a manual command should target: newest live row."""
    rows = store.list_agents(live_only=True, limit=1)
    if not rows:
        return None
    if actor:
        own = [row for row in store.list_agents(live_only=True, limit=200) if row.agent == actor]
        if own:
            return own[0]
    return rows[0]
