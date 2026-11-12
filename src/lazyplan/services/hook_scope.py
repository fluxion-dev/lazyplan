"""Which checkout a hook may gate, and which task owns it.

A hook must never turn an unrelated repository into a gated one. The checkout
is managed only when the database lives in that checkout, a row links the
checkout, or an open session started for planned work belongs to it. The
owning task is the first doing task under a doing plan that resolves to the
same checkout.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..core.entities import Status, Task
from ..core.ports.app import AppPort

LOCAL_PARTS = (".agents", "lazyplan")


@dataclass(frozen=True)
class HookScope:
    """One checkout's gating context."""

    repo: str
    managed: bool = False
    task: Task | None = None

    @property
    def task_id(self) -> int | None:
        """Doing task id, or None."""
        return None if self.task is None else self.task.id


def _local_db(store: AppPort, repo: str) -> bool:
    """True when the database is the checkout's own repo-scoped journal."""
    return Path(store.db_path).resolve().parent == Path(repo).joinpath(*LOCAL_PARTS).resolve()


def _linked_rows(store: AppPort, repo: str) -> set[tuple[str, int]]:
    """Rows with an explicit repo link to this checkout."""
    wanted = store.normalize_repo_path(repo)
    linked: set[tuple[str, int]] = set()
    for (kind, row_id), links in store.repos_map().items():
        for link in links:
            if store.normalize_repo_path(str(link.get("repo_path", ""))) == wanted:
                linked.add((kind, row_id))
                break
    return linked


def _open_session(store: AppPort, repo: str) -> bool:
    """True when an open session started for planned work belongs to this checkout.

    Hooks open a row for every host session in every checkout, so a
    host-bound row without a plan says nothing about the checkout.
    """
    wanted = store.normalize_repo_path(repo)
    for session in store.list_sessions(open_only=True, limit=50):
        if session.host_session and session.plan_id is None:
            continue
        if store.normalize_repo_path(session.repo_path) == wanted:
            return True
    return False


def resolve(store: AppPort, cwd: str | Path | None = None) -> HookScope:
    """Return the managed state and doing task for one checkout."""
    repo = store.checkout_path(str(cwd or Path.cwd()))
    local = _local_db(store, repo)
    linked = _linked_rows(store, repo)
    managed = local or bool(linked) or _open_session(store, repo)
    if not managed:
        return HookScope(repo=repo)

    for plan in store.list_plans():
        if plan.status != Status.DOING:
            continue
        if not local and ("plan", plan.id) not in linked:
            for milestone in store.list_milestones(plan.id):
                if ("milestone", milestone.id) in linked:
                    break
            else:
                continue
        for milestone in store.list_milestones(plan.id):
            for task in store.list_tasks(milestone.id):
                if task.status == Status.DOING:
                    return HookScope(repo=repo, managed=True, task=task)
    return HookScope(repo=repo, managed=True)
