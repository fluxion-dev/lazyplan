"""Application services: use-cases over Store.

Writes and policy go through here: creation (with templates), status
transitions, reconciliation, archival, import/export. Reads and plain
patch-writes may use Store directly (read-model bypass: no pass-through
bloat for policy-free paths). Stdlib only.
"""

from __future__ import annotations

import re
import time

from .kinds import check_kind
from .models import Milestone, Plan, Status, Task
from .store import Store, _ser
from .templates import apply_template, template_criteria

ARCHIVE_AFTER_SECS = 24 * 3600


# -- creation (template fill + auto-criteria live here, not in Store) ------
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


# -- status (rollup policy lives here) --------------------------------------
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


# -- archive (day-old done hides; computed from status history) ------------
def is_archived(store: Store, plan: Plan) -> bool:
    """Done longer than a day, with history to prove it. No proof: never hide."""
    if plan.status != Status.DONE:
        return False
    last = None
    for ts, detail in store.status_events("plan"):
        cleaned = detail.removesuffix(" (rollup)")
        if cleaned.startswith(f"plan #{plan.id} -> "):
            last = (ts, cleaned[len(f"plan #{plan.id} -> ") :])
            break
    if last is None:
        return False
    ts, target = last
    return target == Status.DONE.value and (time.time() - ts) > ARCHIVE_AFTER_SECS


DEFAULT_PLAN_LIMIT = 5


# -- tree (shared list query, composed here) -------------------------------------------------
def plan_activity(store: Store) -> dict[int, float]:
    """Latest event timestamp per plan (whole subtree), for recent-first ordering."""
    with store._connect() as conn:
        mrows = conn.execute("SELECT id, plan_id FROM milestones").fetchall()
        trows = conn.execute("SELECT id, milestone_id FROM tasks").fetchall()
        crows = conn.execute("SELECT id, parent_kind, parent_id FROM criteria").fetchall()
        events = conn.execute("SELECT ts, kind, detail FROM events").fetchall()
    mplan: dict[int, int] = {r["id"]: r["plan_id"] for r in mrows}
    tms: dict[int, int] = {r["id"]: r["milestone_id"] for r in trows}
    crit: dict[int, tuple[str, int]] = {r["id"]: (r["parent_kind"], r["parent_id"]) for r in crows}

    def resolve(kind: str, detail: str) -> int | None:
        m = re.match(r"([PMT])#(\d+)", detail)
        if m:
            letter, oid = m.group(1), int(m.group(2))
            if letter == "P":
                return oid
            if letter == "M":
                return mplan.get(oid)
            chained = tms.get(oid)
            return mplan.get(chained) if chained is not None else None
        m = re.match(r"(plan|milestone|task) #(\d+)", detail)
        if m:
            kind, oid = m.group(1), int(m.group(2))
            if kind == "plan":
                return oid
            if kind == "milestone":
                return mplan.get(oid)
            chained = tms.get(oid)
            return mplan.get(chained) if chained is not None else None
        m = re.match(r"criteria #(\d+)", detail)
        if m:
            found = crit.get(int(m.group(1)))
            if found is None:
                return None
            ckind, pid = found
            if ckind == "plan":
                return pid
            if ckind == "milestone":
                return mplan.get(pid)
            chained = tms.get(pid)
            return mplan.get(chained) if chained is not None else None
        return None

    out: dict[int, float] = {}
    for e in events:
        pid = resolve(e["kind"], e["detail"] or "")
        if pid is not None and e["ts"] > out.get(pid, 0.0):
            out[pid] = e["ts"]
    return out


def _filtered_milestones(
    store: Store,
    plan_id: int,
    status: Status | None,
) -> list[tuple[Milestone, list[Task]]]:
    """Milestone/task pairs of one plan honoring the status filter."""
    milestones = []
    for s in store.list_milestones(plan_id):
        tasks = store.list_tasks(s.id)
        if status is not None:
            tasks = [t for t in tasks if t.status == status]
            if s.status != status and not tasks:
                continue
        milestones.append((s, tasks))
    return milestones


def _repo_match(want: str, repos: list[dict]) -> bool:
    """True when a repo filter matches any effective repo (path or remote)."""
    from pathlib import Path

    needle = (want or "").strip()
    if not needle:
        return True
    try:
        norm = str(Path(needle).expanduser().resolve())
    except OSError:
        norm = str(Path(needle).expanduser().absolute())
    lowered = needle.lower()
    for r in repos:
        path = str(r.get("repo_path", "") or "")
        remote = str(r.get("repo_remote", "") or "")
        if path and (path == norm or path == needle):
            return True
        if remote and (remote == needle or lowered in remote.lower()):
            return True
        if needle in path:
            return True
    return False


def _plan_matches_repo(store: Store, plan_id: int, want: str) -> bool:
    """True when a plan or any descendant effectively links the wanted repo."""
    if _repo_match(want, store.effective_repos("plan", plan_id)):
        return True
    for s in store.list_milestones(plan_id):
        if _repo_match(want, store.effective_repos("milestone", s.id)):
            return True
        for t in store.list_tasks(s.id):
            if _repo_match(want, store.effective_repos("task", t.id)):
                return True
    return False


def _visible_plan(
    store: Store,
    p: Plan,
    milestones: list[tuple[Milestone, list[Task]]],
    status: Status | None,
    archived: str,
) -> bool:
    """Whether a plan survives status/archive filters."""
    arch = is_archived(store, p)
    if archived == "only" and not arch:
        return False
    if archived == "hide" and arch:
        return False
    if status is not None and p.status != status and not milestones:
        return False
    return True


def tree(
    store: Store,
    status: Status | None = None,
    plan_id: int | None = None,
    archived: str = "hide",
    limit: int | None = None,
    repo: str | None = None,
) -> list[tuple[Plan, list[tuple[Milestone, list[Task]]]]]:
    """Nested plans, milestones, and tasks with filters.

    archived: "hide" (default views), "only" (--archived), "show" (--status all).
    Plans order most-recently-active first (id fallback); limit caps the
    plan count (None = all). An explicit plan_id bypasses the cap.
    repo: only plans (or descendants) effectively linked to this repo.
    """
    if archived not in ("hide", "only", "show"):
        raise ValueError("archived must be hide|only|show")
    out = []
    for p in store.list_plans():
        if plan_id is not None and p.id != plan_id:
            continue
        if repo and not _plan_matches_repo(store, p.id, repo):
            continue
        milestones = _filtered_milestones(store, p.id, status)
        if _visible_plan(store, p, milestones, status, archived):
            out.append((p, milestones))
    if plan_id is None:
        activity = plan_activity(store)
        out.sort(key=lambda e: (activity.get(e[0].id, 0.0), e[0].id), reverse=True)
        if limit is not None:
            out = out[: max(limit, 0)]
    return out


# -- export / import (portability) ------------------------------------------
def export_all(store: Store) -> dict:
    """Full dump: plans (with criteria + links + repos) holding milestones and tasks."""
    plans = []
    for p in store.list_plans():
        milestones = []
        for s in store.list_milestones(p.id):
            tasks = []
            for t in store.list_tasks(s.id):
                tasks.append(
                    {
                        "task": _ser(vars(t)),
                        "criteria": [vars(c) for c in store.list_criteria("task", t.id)],
                        "links": [vars(c) for c in store.list_links("task", t.id)],
                        "repos": store.list_repos("task", t.id),
                    }
                )
            milestones.append(
                {
                    "milestone": _ser(vars(s)),
                    "criteria": [vars(c) for c in store.list_criteria("milestone", s.id)],
                    "links": [vars(c) for c in store.list_links("milestone", s.id)],
                    "repos": store.list_repos("milestone", s.id),
                    "tasks": tasks,
                }
            )
        plans.append(
            {
                "plan": _ser(vars(p)),
                "criteria": [vars(c) for c in store.list_criteria("plan", p.id)],
                "links": [vars(c) for c in store.list_links("plan", p.id)],
                "repos": store.list_repos("plan", p.id),
                "milestones": milestones,
            }
        )
    return {"lazyplan": 1, "plans": plans}


def export_plan(store: Store, plan_id: int) -> dict | None:
    """Single-plan entry in export_all() shape (or None when missing)."""
    plans: list[dict] = export_all(store)["plans"]
    for entry in plans:
        plan: dict = entry["plan"]
        if plan["id"] == plan_id:
            return entry
    return None


def import_all(store: Store, data: dict, actor: str = "human") -> dict[str, int]:
    """Load an export_all() dump. Returns counts.

    Template fill is skipped on import: the dump carries final values.
    """
    if not isinstance(data, dict) or data.get("lazyplan") != 1:
        raise ValueError("not a lazyplan export (missing lazyplan: 1)")
    counts = {"plans": 0, "milestones": 0, "tasks": 0, "criteria": 0, "links": 0, "repos": 0}

    def _apply_status(kind: str, obj_id: int, status: str) -> None:
        if status and status != Status.TODO.value:
            set_status(store, kind, obj_id, Status(status), actor=actor)

    def _import_criteria(kind: str, obj_id: int, items: list) -> None:
        for c in items:
            nc = store.add_criteria(kind, obj_id, c.get("text", ""), actor=actor)
            if c.get("done"):
                store.set_criteria(nc.id, True, actor=actor)
            counts["criteria"] += 1

    def _import_links(kind: str, obj_id: int, items: list) -> None:
        for c in items:
            sha = str(c.get("sha", "") or "").strip()
            if not sha:
                continue
            try:
                store.link_commit(
                    kind,
                    obj_id,
                    sha,
                    subject=str(c.get("subject", "") or ""),
                    author=str(c.get("author", "") or ""),
                    timestamp=int(c.get("timestamp", 0) or 0),
                    repo_root=str(c.get("repo_root", "") or ""),
                    actor=actor,
                )
            except ValueError:
                continue
            counts["links"] += 1

    def _import_repos(kind: str, obj_id: int, items: list) -> None:
        for r in items:
            path = str(r.get("repo_path", "") or "").strip()
            if not path:
                continue
            try:
                store.add_repo_link(
                    kind,
                    obj_id,
                    path,
                    repo_remote=str(r.get("repo_remote", "") or ""),
                    actor=actor,
                )
            except (ValueError, KeyError):
                continue
            counts["repos"] = counts.get("repos", 0) + 1

    for entry in data.get("plans", []):
        p = entry["plan"]
        np = store.add_plan(
            p.get("name", p.get("title", "imported")),
            p.get("description", ""),
            goal=p.get("goal", ""),
            actor=actor,
        )
        _apply_status("plan", np.id, p.get("status", ""))
        counts["plans"] += 1
        _import_criteria("plan", np.id, entry.get("criteria", []))
        _import_links("plan", np.id, entry.get("links", []))
        _import_repos("plan", np.id, entry.get("repos", []))
        for sentry in entry.get("milestones", []):
            sp = sentry["milestone"]
            ns = store.add_milestone(
                np.id,
                sp.get("title", ""),
                sp.get("description", ""),
                actor=actor,
            )
            _apply_status("milestone", ns.id, sp.get("status", ""))
            counts["milestones"] += 1
            _import_criteria("milestone", ns.id, sentry.get("criteria", []))
            _import_links("milestone", ns.id, sentry.get("links", []))
            _import_repos("milestone", ns.id, sentry.get("repos", []))
            for tentry in sentry.get("tasks", []):
                tp = tentry["task"]
                nt = store.add_task(
                    ns.id,
                    tp.get("title", ""),
                    description=tp.get("description", ""),
                    actor=actor,
                )
                _apply_status("task", nt.id, tp.get("status", ""))
                counts["tasks"] += 1
                _import_criteria("task", nt.id, tentry.get("criteria", []))
                _import_links("task", nt.id, tentry.get("links", []))
                _import_repos("task", nt.id, tentry.get("repos", []))
        # Milestones landed after the plan's own status: recompute it.
        heal(store, "plan", np.id, actor)
    return counts
