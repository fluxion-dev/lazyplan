"""Plan-level sync: add unknown uids, skip identical plans, report conflicts.

No deletes and no overwrites. Row-level merge is intentionally out of scope.
"""

from __future__ import annotations

from . import services
from .store import Store


def _summary(entry: dict) -> dict:
    plan = entry.get("plan", {})
    milestones = entry.get("milestones", [])
    tasks = sum(len(item.get("tasks", [])) for item in milestones)
    criteria = len(entry.get("criteria", []))
    for milestone in milestones:
        criteria += len(milestone.get("criteria", []))
        for task in milestone.get("tasks", []):
            criteria += len(task.get("criteria", []))
    return {
        "name": str(plan.get("name", "")),
        "why": str(plan.get("goal", "")),
        "what": str(plan.get("description", "")),
        "status": str(plan.get("status", "")),
        "milestones": len(milestones),
        "tasks": tasks,
        "criteria": criteria,
    }


def _differences(local: dict, incoming: dict) -> list[str]:
    left = _summary(local)
    right = _summary(incoming)
    return [key for key in left if left[key] != right[key]]


def sync(store: Store, data: dict, actor: str = "human", dry_run: bool = False) -> dict:
    """Merge a dump by plan uid; returns adds, skips, and conflicts."""
    if not isinstance(data, dict) or data.get("lazyplan") != 1:
        raise ValueError("not a lazyplan export (missing lazyplan: 1)")
    report: dict = {"dry_run": dry_run, "added": [], "skipped": [], "conflicts": []}
    seen: set[str] = set()
    for entry in data.get("plans", []):
        if not isinstance(entry, dict):
            continue
        plan = entry.get("plan", {})
        uid = str(plan.get("uid", "") or "").strip()
        title = str(plan.get("name", "") or "(untitled)")
        if uid and uid in seen:
            report["conflicts"].append(
                {"uid": uid, "title": title, "local_id": 0, "differences": ["duplicate-uid"]}
            )
            continue
        if uid:
            seen.add(uid)
        local = store.get_plan_by_uid(uid) if uid else None
        if local is None:
            if not dry_run:
                created = services.import_all(store, {"lazyplan": 1, "plans": [entry]}, actor=actor)
                local_id = 0
                if created.get("plans"):
                    match = store.get_plan_by_uid(uid) if uid else None
                    local_id = match.id if match is not None else 0
            else:
                local_id = 0
            report["added"].append({"uid": uid, "title": title, "local_id": local_id})
            continue
        local_entry = services.export_plan(store, local.id)
        differences = _differences(local_entry or {}, entry)
        if differences:
            report["conflicts"].append(
                {
                    "uid": uid,
                    "title": title,
                    "local_id": local.id,
                    "differences": differences,
                }
            )
        else:
            report["skipped"].append({"uid": uid, "title": title, "local_id": local.id})
    return report
