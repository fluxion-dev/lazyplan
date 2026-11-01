"""Compatibility shim for planning; link refresh moves to provenance."""

from __future__ import annotations

import time
from pathlib import Path

from ..kinds import check_kind
from ..store import Store
from ..vcs import detect_backend
from .planning import (
    _rollup_target,
    create_milestone,
    create_plan,
    create_task,
    cycle_status,
    heal,
    heal_parents,
    reconcile,
    set_status,
)

__all__ = [
    "_rollup_target",
    "create_milestone",
    "create_plan",
    "create_task",
    "cycle_status",
    "heal",
    "heal_parents",
    "reconcile",
    "refresh_links",
    "set_status",
]


def refresh_links(
    store: Store,
    kind: str,
    obj_id: int,
    actor: str = "human",
    cwd: str = ".",
) -> dict[str, int]:
    """Re-resolve cached commit links; mark missing commits stale."""
    check_kind(kind)
    now = int(time.time())
    links = store.effective_links(kind, obj_id)
    updated = 0
    stale = 0
    for link in links:
        info = None
        target = link.repo_root or cwd
        if not link.repo_root or Path(link.repo_root).is_dir():
            backend, root = detect_backend(target)
            if backend is not None and root is not None:
                info = backend.show(root, link.sha)
        if info is None:
            store.update_link(
                link.id,
                subject=link.subject,
                author=link.author,
                timestamp=link.timestamp,
                repo_root=link.repo_root,
                stale=True,
                checked_at=now,
                actor=actor,
            )
            stale += 1
            continue
        store.update_link(
            link.id,
            subject=info.subject,
            author=info.author,
            timestamp=info.timestamp,
            repo_root=info.repo_root,
            stale=False,
            checked_at=now,
            files=info.files,
            actor=actor,
        )
        updated += 1
    return {"checked": len(links), "updated": updated, "stale": stale}
