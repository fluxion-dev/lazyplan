"""Provenance use cases: commits, repos, forge links, source, and gates."""

from __future__ import annotations

import time
from pathlib import Path

from lazyplan.infrastructure.vcs import detect_backend

from ..core.kinds import check_kind
from ..core.ports.provenance import ProvenancePort
from .forge import (
    _checks_state,
    _forge_target,
    _link_forge_target,
    _pr_checks,
    _pr_number,
    _pr_reviews,
    _pr_state,
    _store_pr,
    _store_pulls,
    _tasks_in_scope,
    forge_statuses,
    refresh_forge,
)
from .tasks import (
    _finish_target,
    _gate_failure,
    _link_commits,
    finish_task,
    gate_state,
    start_task,
)
from .vcs import (
    _branch_ref,
    _branch_scan,
    _capture_block,
    _ensure_task_repo_links,
    _norm_path,
    _repo_for_task,
    _repo_targets,
    _scan_ref_action,
    _scan_wanted,
    _task_capture_block,
    _trailer_refs,
    auto_capture_head,
    repo_statuses,
    scan_commits,
)


def refresh_links(
    port: ProvenancePort,
    kind: str,
    obj_id: int,
    actor: str = "human",
    cwd: str = ".",
) -> dict[str, int]:
    """Re-resolve cached commit links; mark missing commits stale."""
    check_kind(kind)
    now = int(time.time())
    links = port.effective_links(kind, obj_id)
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
            port.update_link(
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
        port.update_link(
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


__all__ = [
    "_branch_ref",
    "_branch_scan",
    "_capture_block",
    "_checks_state",
    "_ensure_task_repo_links",
    "_finish_target",
    "_forge_target",
    "_gate_failure",
    "_link_commits",
    "_link_forge_target",
    "_norm_path",
    "_pr_checks",
    "_pr_number",
    "_pr_reviews",
    "_pr_state",
    "_repo_for_task",
    "_repo_targets",
    "_scan_ref_action",
    "_scan_wanted",
    "_store_pr",
    "_store_pulls",
    "_tasks_in_scope",
    "_task_capture_block",
    "_trailer_refs",
    "auto_capture_head",
    "finish_task",
    "forge_statuses",
    "gate_state",
    "refresh_forge",
    "refresh_links",
    "repo_statuses",
    "scan_commits",
    "start_task",
]
