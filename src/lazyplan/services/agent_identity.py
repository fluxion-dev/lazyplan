"""Exact agent identity, git facts, and plan/task binding."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from ..core.policies.agents import (
    normalize_name,
    normalize_path,
    normalize_role,
    normalize_session_id,
    parse_pid,
)
from ..core.ports.app import AppPort
from ..infrastructure.process import process_start
from ..infrastructure.repo import find_repo_root, git_common_dir
from . import attribution


@dataclass(frozen=True)
class GitFacts:
    """Repo, worktree, branch, and HEAD for one host's working directory."""

    repo_path: str = ""
    worktree: str = ""
    branch: str = ""
    head_sha: str = ""


@dataclass(frozen=True)
class Binding:
    """The exact plan, task, and worktree an agent proves."""

    plan_id: int | None = None
    task_id: int | None = None
    worktree: str = ""
    reason: str = ""


@dataclass(frozen=True)
class AgentIdentity:
    """Normalized identity from one host payload or manual command."""

    host: str = "unknown"
    host_session: str = ""
    agent: str = "unknown"
    role: str = "primary"
    model: str = "unknown"
    parent_session: str = ""
    pid: int = 0
    process_start: str = ""
    cwd: str = ""


def _nested(payload: dict, *keys: str) -> object:
    """First present value across the payload and its common nested maps."""
    for key in keys:
        value = payload.get(key)
        if value not in (None, ""):
            return value
    for name in ("data", "info", "agent"):
        inner = payload.get(name)
        if isinstance(inner, dict):
            for key in keys:
                value = inner.get(key)
                if value not in (None, ""):
                    return value
    return ""


def host_session_id(payload: dict) -> str:
    """The host's own session id from the common payload shapes."""
    return normalize_session_id(
        _nested(
            payload,
            "host_session",
            "hostSession",
            "session_id",
            "sessionID",
            "thread_id",
            "sessionId",
        )
    )


def parent_session_id(payload: dict) -> str:
    """The parent host session id when this payload describes a subagent."""
    return normalize_session_id(
        _nested(
            payload,
            "parent_session",
            "parentSession",
            "parent_session_id",
            "parentID",
            "parent_id",
            "parentAgent",
        )
    )


def extract_identity(
    host: str,
    payload: dict,
    cwd: str | Path | None = None,
    pid: int | None = None,
) -> AgentIdentity:
    """Normalize one host payload; missing facts stay explicitly unknown."""
    here = str(cwd or payload.get("cwd") or payload.get("directory") or Path.cwd())
    session = host_session_id(payload)
    parent = parent_session_id(payload)
    role = normalize_role(str(_nested(payload, "role", "agent_role", "agentRole") or ""))
    if _nested(payload, "subagent_type", "agent_type", "agentType") and role == "primary":
        role = "subagent"
    if parent and role == "primary":
        role = "subagent"
    agent_pid = parse_pid(_nested(payload, "pid", "process_id", "processID"))
    if not agent_pid and pid is not None:
        agent_pid = parse_pid(pid)
    return AgentIdentity(
        host=normalize_name(host),
        host_session=session,
        agent=normalize_name(
            _nested(
                payload,
                "agent",
                "agent_name",
                "agentName",
                "agent_id",
                "agent_type",
                "subagent_type",
                "name",
            )
        ),
        role=role,
        model=normalize_name(
            _nested(payload, "model", "model_id", "modelID", "modelId", "model_name")
        ),
        parent_session=parent,
        pid=agent_pid,
        process_start=process_start(agent_pid) if agent_pid else "",
        cwd=normalize_path(here),
    )


def git_facts(cwd: str | Path | None = None) -> GitFacts:
    """Read repo, worktree, branch, and HEAD without writing anything."""
    here = Path(cwd or Path.cwd()).expanduser()
    root = find_repo_root(here)
    if root is None:
        return GitFacts()
    worktree = str(root)
    common = git_common_dir(worktree)
    repo = str(Path(common).parent) if common else worktree
    branch = attribution.current_branch(worktree)
    head = ""
    try:
        from ..infrastructure.vcs import GitBackend

        head = GitBackend().head(worktree) or ""
    except (OSError, RuntimeError, ValueError):
        head = ""
    return GitFacts(
        repo_path=normalize_path(repo),
        worktree=normalize_path(worktree),
        branch=branch,
        head_sha=head,
    )


def _same_path(store: AppPort, left: str, right: str) -> bool:
    """True when two checkout paths name the same directory."""
    if not left or not right:
        return False
    return store.normalize_repo_path(left) == store.normalize_repo_path(right)


def _registered_plans(store: AppPort, worktree: str) -> list[int]:
    """Plans whose registered worktree is exactly this checkout."""
    found: list[int] = []
    for plan in store.list_plans(archived="show"):
        if any(
            _same_path(store, row.worktree_path, worktree)
            for row in store.list_plan_worktrees(plan.id)
        ):
            found.append(plan.id)
    return found


def _claimed_task(store: AppPort, plan_id: int, worktree: str, repo: str) -> int | None:
    """The newest active claim for this plan in this worktree, if unambiguous."""
    now = time.time()
    matches = [
        claim
        for claim in store.list_claims()
        if int(claim.get("plan_id") or 0) == plan_id
        and not bool(claim.get("expired"))
        and (
            not str(claim.get("worktree") or claim.get("repo_path") or "").strip()
            or _same_path(store, str(claim.get("worktree") or ""), worktree)
            or _same_path(store, str(claim.get("repo_path") or ""), repo)
        )
        and float(claim.get("expires_at") or 0) > now
    ]
    if not matches:
        return None
    matches.sort(key=lambda row: float(row.get("started_at") or 0), reverse=True)
    return int(matches[0]["task_id"])


def resolve_binding(
    store: AppPort,
    worktree: str,
    repo_path: str = "",
    explicit_plan: int | None = None,
) -> Binding:
    """Bind a plan and task from the worktree registry and the active claim."""
    if explicit_plan is not None:
        plan = store.get_plan(explicit_plan)
        if plan is None:
            raise KeyError(f"plan #{explicit_plan} not found")
        rows = store.list_plan_worktrees(explicit_plan)
        match = next((row for row in rows if _same_path(store, row.worktree_path, worktree)), None)
        if match is None:
            expected = ", ".join(row.worktree_path for row in rows)
            reason = (
                f"plan #{explicit_plan} is not registered in a registered worktree:"
                f" {worktree or 'this checkout'}"
                + (f"; expected {expected}" if expected else "")
                + f"; run `lpui plan worktree --print --id {explicit_plan}`"
            )
            return Binding(worktree=worktree, reason=reason)
        task_id = _claimed_task(store, explicit_plan, worktree, repo_path)
        return Binding(plan_id=explicit_plan, task_id=task_id, worktree=worktree)
    plans = _registered_plans(store, worktree)
    if len(plans) == 1:
        plan_id = plans[0]
        task_id = _claimed_task(store, plan_id, worktree, repo_path)
        return Binding(plan_id=plan_id, task_id=task_id, worktree=worktree)
    if len(plans) > 1:
        names = ", ".join(f"P{plan_id}" for plan_id in plans)
        return Binding(
            worktree=worktree,
            reason=f"{worktree} is registered to more than one plan ({names})",
        )
    return Binding(
        worktree=worktree,
        reason=f"{worktree or 'this checkout'} is not a registered plan worktree",
    )
