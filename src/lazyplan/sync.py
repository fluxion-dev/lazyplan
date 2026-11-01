"""Plan-level sync: add unknown uids, skip identical plans, report conflicts.

No deletes and no overwrites. Row-level merge is intentionally out of scope.
"""

from __future__ import annotations

from . import services
from .core.policies.transfer import differences, is_export
from .core.ports.transfer import TransferPort


def sync(store: TransferPort, data: dict, actor: str = "human", dry_run: bool = False) -> dict:
    """Merge a dump by plan uid; returns adds, skips, and conflicts."""
    if not is_export(data):
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
        changed = differences(local_entry or {}, entry)
        if changed:
            report["conflicts"].append(
                {
                    "uid": uid,
                    "title": title,
                    "local_id": local.id,
                    "differences": changed,
                }
            )
        else:
            report["skipped"].append({"uid": uid, "title": title, "local_id": local.id})
    return report
