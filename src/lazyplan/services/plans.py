"""Plans services."""

from __future__ import annotations

import time
from pathlib import Path

from ..kinds import check_kind
from ..models import Milestone, Plan, Status, Task
from ..store import Store
from ..templates import apply_template, template_criteria
from ..vcs import detect_backend


def create_plan(
    store: Store,
    name: str,
    description: str = "",
    goal: str = "",
    actor: str = "human",
) -> Plan:
    """Insert a plan with template defaults and auto-criteria."""
    filled = apply_template(
        "plan",
        {"title": name, "why": goal, "what": description},
        store.path,
    )
    p = store.add_plan(
        name=filled["title"].strip(),
        description=filled["what"],
        goal=filled["why"],
        actor=actor,
    )
    for text in template_criteria("plan", store.path):
        store.add_criteria("plan", p.id, text, actor=actor)
    return p


def create_milestone(
    store: Store,
    plan_id: int,
    title: str,
    description: str = "",
    actor: str = "human",
) -> Milestone:
    """Insert a milestone with template defaults and auto-criteria."""
    filled = apply_template(
        "milestone",
        {"title": title, "desc": description},
        store.path,
    )
    s = store.add_milestone(
        plan_id=plan_id,
        title=filled["title"].strip(),
        description=filled["desc"],
        actor=actor,
    )
    for text in template_criteria("milestone", store.path):
        store.add_criteria("milestone", s.id, text, actor=actor)
    return s


def create_task(
    store: Store,
    milestone_id: int,
    title: str,
    description: str = "",
    actor: str = "human",
) -> Task:
    """Insert a task with template defaults and auto-criteria."""
    filled = apply_template(
        "task",
        {"title": title, "desc": description},
        store.path,
    )
    t = store.add_task(
        milestone_id=milestone_id,
        title=filled["title"].strip(),
        description=filled["desc"],
        actor=actor,
    )
    for text in template_criteria("task", store.path):
        store.add_criteria("task", t.id, text, actor=actor)
    return t


def _rollup_target(statuses: list[Status]) -> Status:
    """Parent state from children: all done -> done, any doing -> doing, else todo."""
    if all(s == Status.DONE for s in statuses):
        return Status.DONE
    if any(s == Status.DOING for s in statuses):
        return Status.DOING
    return Status.TODO


def heal(store: Store, kind: str, obj_id: int, actor: str = "human") -> bool:
    """Recompute one milestone/plan from its children. Returns changed."""
    check_kind(kind)
    obj: Plan | Milestone | None
    if kind == "milestone":
        obj = store.get_milestone(obj_id)
        kids = [t.status for t in store.list_tasks(obj_id)] if obj is not None else []
    elif kind == "plan":
        obj = store.get_plan(obj_id)
        kids = [s.status for s in store.list_milestones(obj_id)] if obj is not None else []
    else:
        raise ValueError("kind must be milestone|plan")
    if obj is None or not kids:
        return False
    target = _rollup_target(kids)
    if obj.status == target:
        return False
    store.set_status_raw(kind, obj_id, target)
    store.log(actor, kind, "status", f"{kind} #{obj_id} -> {target.value} (rollup)")
    return True


def heal_parents(store: Store, kind: str, obj_id: int, actor: str = "human") -> None:
    """Recompute ancestors after a status write; childless rows keep manual status."""
    check_kind(kind)
    if kind == "task":
        t = store.get_task(obj_id)
        if t is None:
            return
        heal(store, "milestone", t.milestone_id, actor)
        s = store.get_milestone(t.milestone_id)
        if s is not None:
            heal(store, "plan", s.plan_id, actor)
    elif kind == "milestone":
        heal(store, "milestone", obj_id, actor)
        s = store.get_milestone(obj_id)
        if s is not None:
            heal(store, "plan", s.plan_id, actor)
    elif kind == "plan":
        heal(store, "plan", obj_id, actor)


def set_status(store: Store, kind: str, obj_id: int, status: Status, actor: str = "human") -> bool:
    """Move a row, heal the subtree state, and log the transition."""
    check_kind(kind)
    ok = store.set_status_raw(kind, obj_id, status)
    if ok:
        store.log(actor, kind, "status", f"{kind} #{obj_id} -> {status.value}")
        heal_parents(store, kind, obj_id, actor)
    return ok


def cycle_status(store: Store, kind: str, obj_id: int, actor: str = "human") -> Status | None:
    """Advance todo to doing to done to todo."""
    check_kind(kind)
    order = [Status.TODO, Status.DOING, Status.DONE]
    obj = store.get_parent(kind, obj_id)
    if obj is None:
        return None
    nxt = order[(order.index(obj.status) + 1) % len(order)]
    set_status(store, kind, obj_id, nxt, actor=actor)
    return nxt


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


def reconcile(store: Store, actor: str = "human") -> list[dict]:
    """Recompute every parent from its children; childless rows untouched."""
    changes: list[dict] = []
    for p in store.list_plans():
        before_p = p.status
        for s in store.list_milestones(p.id):
            before = s.status
            heal(store, "milestone", s.id, actor)
            after = store.get_milestone(s.id)
            if after is not None and after.status != before:
                changes.append({"kind": "milestone", "id": s.id, "to": after.status.value})
        heal(store, "plan", p.id, actor)
        after_p = store.get_plan(p.id)
        if after_p is not None and after_p.status != before_p:
            changes.append({"kind": "plan", "id": p.id, "to": after_p.status.value})
    return changes
