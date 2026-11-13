"""Plan worktree CLI commands."""

from __future__ import annotations

import argparse
import os
import sys

from lazyplan.services.worktrees import (
    done_blocker,
    removal_commands,
    verify_worktree,
    worktree_gate,
)

from ....core.entities import Plan, PlanWorktree
from ....core.policies.worktrees import WorktreeCollision, derive_worktree, derive_worktrees
from ....core.ports.app import AppPort
from ....core.ports.insights import InsightsPort
from ....core.serialization import to_payload
from ...shared import porcelain
from ...shared.design import msg_error, msg_not_found
from ..emit import _emit


def _quote_path(text: str) -> str:
    """Quote one shell path only when it needs it."""
    if any(char.isspace() for char in text):
        return f'"{text}"'
    return text


def _print_plan_worktrees(
    store: AppPort,
    plan: Plan,
    args: argparse.Namespace,
    actor: str,
) -> int:
    """Print one setup command per linked repo."""
    repos = store.list_repos("plan", plan.id)
    if not repos:
        store.add_repo_link("plan", plan.id, store.checkout_path(), actor=actor)
        repos = store.list_repos("plan", plan.id)
    try:
        targets = derive_worktrees(
            [str(repo["repo_path"]) for repo in repos],
            plan.id,
            plan.name,
            exists=os.path.exists,
        )
    except (ValueError, WorktreeCollision) as exc:
        print(msg_error(exc), file=sys.stderr)
        return 2
    entries = []
    for repo, target in zip(repos, targets, strict=True):
        start = str(repo.get("base_sha") or repo.get("branch") or "HEAD")
        command = (
            f"git -C {_quote_path(target.repo_path)} worktree add -b {target.branch}"
            f" {_quote_path(target.worktree_path)} {_quote_path(start)}"
        )
        entries.append(
            {
                "repo_path": target.repo_path,
                "worktree_path": target.worktree_path,
                "branch": target.branch,
                "command": command,
            }
        )
    if args.json:
        return _emit(args, {"plan": to_payload(vars(plan)), "worktrees": entries})
    if porcelain.enabled(args):
        for entry in entries:
            print(
                porcelain.row(
                    "worktree",
                    plan.id,
                    "ready",
                    entry["branch"],
                    f"plan:{plan.id}",
                    entry["worktree_path"],
                )
            )
        return 0
    print(f"plan {plan.id}: {plan.name}")
    for entry in entries:
        print(f"repo {entry['repo_path']}")
        print(f"  {entry['command']}")
    return 0


def _emit_worktree(
    args: argparse.Namespace,
    plan: Plan,
    row: PlanWorktree,
    state: str,
) -> int:
    """Print one registration result in the selected format."""
    payload = {"plan": to_payload(vars(plan)), "worktree": to_payload(vars(row))}
    if args.json:
        return _emit(args, payload)
    if porcelain.enabled(args):
        print(
            porcelain.row(
                "worktree",
                plan.id,
                state,
                row.branch,
                f"plan:{plan.id}",
                row.worktree_path,
            )
        )
        return 0
    print(f"{state} plan {plan.id} worktree {row.worktree_path} on {row.branch}")
    return 0


def _linked_repos(store: AppPort, plan_id: int) -> dict[str, dict]:
    """Linked repos keyed by resolved path."""
    return {
        store.resolve_repo_path(str(row["repo_path"])): row
        for row in store.list_repos("plan", plan_id)
    }


def _register_plan_worktree(
    store: AppPort, plan: Plan, args: argparse.Namespace, actor: str
) -> int:
    """Validate and register one worktree for a linked repo."""
    repo = store.resolve_repo_path(args.repo)
    repos = _linked_repos(store, plan.id)
    if not repos:
        store.add_repo_link("plan", plan.id, repo, actor=actor)
        repos = _linked_repos(store, plan.id)
    if repo not in repos:
        print(
            msg_error(ValueError(f"repo is not linked to plan #{plan.id}: {repo}")),
            file=sys.stderr,
        )
        return 2

    target = derive_worktree(repo, plan.id, plan.name)
    worktree = store.resolve_repo_path(args.worktree) if args.worktree else target.worktree_path
    branch = args.branch or target.branch
    check = verify_worktree(repo, worktree, branch)
    if not check.ok:
        print(msg_error(ValueError(check.reason)), file=sys.stderr)
        return 2

    existing = store.get_plan_worktree(plan.id, repo)
    if existing is not None and existing.worktree_path == worktree and existing.branch == branch:
        return _emit_worktree(args, plan, existing, "already-registered")

    row = store.register_plan_worktree(
        plan.id,
        repo,
        worktree,
        branch=branch,
        repo_remote=str(repos[repo].get("repo_remote", "")),
        actor=actor,
    )
    return _emit_worktree(args, plan, row, "registered")


def _remove_plan_worktree(store: AppPort, plan: Plan, args: argparse.Namespace, actor: str) -> int:
    """Unregister one repo after a clean check; a missing checkout may still go."""
    repo = store.resolve_repo_path(args.repo)
    existing = store.get_plan_worktree(plan.id, repo)
    if existing is None:
        print(
            msg_error(ValueError(f"plan #{plan.id} has no worktree for {repo}")),
            file=sys.stderr,
        )
        return 1

    if os.path.exists(existing.worktree_path):
        check = verify_worktree(existing.repo_path, existing.worktree_path, existing.branch)
        if not check.ok:
            print(msg_error(ValueError(check.reason)), file=sys.stderr)
            return 2

    store.remove_plan_worktree(plan.id, repo, actor=actor)
    return _emit_worktree(args, plan, existing, "removed")


def guard_plan_done(store: InsightsPort, plan_id: int) -> int:
    """Refuse a dirty worktree, else print the removal commands."""
    blocked = done_blocker(store, plan_id)
    if blocked:
        print(msg_error(ValueError(blocked)), file=sys.stderr)
        return 2
    for command in removal_commands(store, plan_id):
        print(f"remove: {command}", file=sys.stderr)
    return 0


def _guard_plan_start(store: InsightsPort, args: argparse.Namespace) -> tuple[str, int]:
    """Worktree refusal and exit code for a plan start."""
    if getattr(args, "kind", "") != "plan" or getattr(args, "to", "") != "doing":
        return "", 0
    failure = worktree_gate(store, args.id)
    if not failure:
        return "", 0
    if not getattr(args, "force", False):
        return failure, 2
    if not str(getattr(args, "reason", "") or "").strip():
        return "--force needs --reason", 2
    return failure, 0


def record_worktree_override(store: InsightsPort, plan_id: int, actor: str, reason: str) -> None:
    """Record that an agent forced an isolated plan start."""
    store.add_note(
        "plan",
        plan_id,
        f"Worktree gate override by {actor}: {reason}",
        actor=actor,
    )


def _cmd_plan_worktree(store: AppPort, args: argparse.Namespace, actor: str) -> int:
    """Print, register, or remove plan worktrees."""
    if args.id is None:
        print("error: plan worktree needs --id", file=sys.stderr)
        return 2
    plan = store.get_plan(args.id)
    if plan is None:
        print(msg_not_found("plan", args.id), file=sys.stderr)
        return 1
    action = getattr(args, "worktree_action", None)
    if action == "add":
        return _register_plan_worktree(store, plan, args, actor)
    if action == "remove":
        return _remove_plan_worktree(store, plan, args, actor)
    return _print_plan_worktrees(store, plan, args, actor)
