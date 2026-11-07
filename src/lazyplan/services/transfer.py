"""Transfer services."""

from __future__ import annotations

from typing import Any

from ..core.entities import Criterion, Plan, Status, Task
from ..core.ports.transfer import TransferPort
from ..core.serialization import to_payload
from .planning import heal, set_status


def _export_maps(store: TransferPort) -> dict[str, Any]:
    """Every child table loaded once for an export."""
    return {
        "milestones": store.milestones_map(),
        "tasks": store.tasks_map(),
        "criteria": store.criteria_map(),
        "links": store.vcs_links_map(),
        "forge": store.forge_links_map(),
        "repos": store.repos_map(),
        "notes": store.notes_full_map(),
        "comments": store.comments_full_map(),
        "issues": store.issue_links_map(),
        "claims": store.claims_map(),
        "uids": store.plan_uids_map(),
        "evidence": store.evidence_map(),
    }


def _export_entry(plan: Plan, maps: dict[str, Any]) -> dict:
    """One plan entry in export_all() shape from preloaded maps."""
    criteria = maps["criteria"]
    links = maps["links"]
    forge = maps["forge"]
    repos = maps["repos"]
    notes = maps["notes"]
    comments = maps["comments"]
    issues = maps["issues"]
    claims = maps["claims"]
    evidence = maps["evidence"]

    def criterion_entry(item: Criterion) -> dict:
        data = vars(item)
        rows = evidence.get(item.id, [])
        if rows:
            data["evidence"] = [vars(row) for row in rows]
        return data

    def task_entry(task: Task) -> dict:
        claim = claims.get(task.id)
        return {
            "task": to_payload(vars(task)),
            "criteria": [criterion_entry(item) for item in criteria.get(("task", task.id), [])],
            "links": [vars(item) for item in links.get(("task", task.id), [])],
            "forge_links": [vars(item) for item in forge.get(("task", task.id), [])],
            "repos": repos.get(("task", task.id), []),
            "notes": [vars(item) for item in notes.get(("task", task.id), [])],
            "comments": [vars(item) for item in comments.get(("task", task.id), [])],
            "issues": issues.get(("task", task.id), []),
            "claim": vars(claim) if claim is not None else None,
        }

    milestone_entries = []
    for milestone in maps["milestones"].get(plan.id, ()):
        milestone_entries.append(
            {
                "milestone": to_payload(vars(milestone)),
                "criteria": [
                    criterion_entry(item) for item in criteria.get(("milestone", milestone.id), [])
                ],
                "links": [vars(item) for item in links.get(("milestone", milestone.id), [])],
                "forge_links": [vars(item) for item in forge.get(("milestone", milestone.id), [])],
                "repos": repos.get(("milestone", milestone.id), []),
                "notes": [vars(item) for item in notes.get(("milestone", milestone.id), [])],
                "comments": [vars(item) for item in comments.get(("milestone", milestone.id), [])],
                "issues": issues.get(("milestone", milestone.id), []),
                "tasks": [task_entry(task) for task in maps["tasks"].get(milestone.id, ())],
            }
        )
    return {
        "plan": {**to_payload(vars(plan)), "uid": maps["uids"].get(plan.id, "")},
        "criteria": [criterion_entry(item) for item in criteria.get(("plan", plan.id), [])],
        "links": [vars(item) for item in links.get(("plan", plan.id), [])],
        "forge_links": [vars(item) for item in forge.get(("plan", plan.id), [])],
        "repos": repos.get(("plan", plan.id), []),
        "notes": [vars(item) for item in notes.get(("plan", plan.id), [])],
        "comments": [vars(item) for item in comments.get(("plan", plan.id), [])],
        "issues": issues.get(("plan", plan.id), []),
        "milestones": milestone_entries,
    }


def export_all(store: TransferPort) -> dict:
    """Full dump: plans (with criteria + links + repos) holding milestones and tasks."""
    maps = _export_maps(store)
    return {
        "lazyplan": 1,
        "plans": [_export_entry(plan, maps) for plan in store.list_plans()],
        "criterion_links": store.all_criterion_links(),
    }


def export_plan(store: TransferPort, plan_id: int) -> dict | None:
    """Single-plan entry in export_all() shape (or None when missing)."""
    plan = store.get_plan(plan_id)
    if plan is None:
        return None
    return _export_entry(plan, _export_maps(store))


def import_all(store: TransferPort, data: dict, actor: str = "human") -> dict[str, int]:
    """Load an export_all() dump atomically; returns counts."""
    with store.transaction():
        return _import_all(store, data, actor)


def _import_all(store: TransferPort, data: dict, actor: str = "human") -> dict[str, int]:
    """Load an export_all() dump. Returns counts.

    Template fill is skipped on import: the dump carries final values.
    """
    if not isinstance(data, dict) or data.get("lazyplan") != 1:
        raise ValueError("not a lazyplan export (missing lazyplan: 1)")
    counts = {
        "plans": 0,
        "milestones": 0,
        "tasks": 0,
        "criteria": 0,
        "links": 0,
        "repos": 0,
        "forge_links": 0,
        "claims": 0,
        "notes": 0,
        "criterion_links": 0,
        "comments": 0,
        "issues": 0,
        "evidence": 0,
    }
    criteria_map: dict[int, int] = {}
    tasks_map: dict[int, int] = {}
    evidence_items: list[tuple[int, dict]] = []

    def _apply_status(kind: str, obj_id: int, status: str) -> None:
        if status and status != Status.TODO.value:
            set_status(store, kind, obj_id, Status(status), actor=actor)

    def _import_criteria(kind: str, obj_id: int, items: list) -> None:
        for c in items:
            nc = store.add_criteria(kind, obj_id, c.get("text", ""), actor=actor)
            if c.get("done"):
                store.set_criteria(nc.id, True, actor=actor)
            criteria_map[int(c.get("id", 0) or 0)] = nc.id
            counts["criteria"] += 1
            for row in c.get("evidence", []):
                if isinstance(row, dict):
                    evidence_items.append((nc.id, row))

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
                    files=tuple(str(p) for p in c.get("files", []) if isinstance(p, str)),
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
                    branch=str(r.get("branch", "") or ""),
                    base_sha=str(r.get("base_sha", "") or ""),
                    actor=actor,
                )
            except (ValueError, KeyError):
                continue
            counts["repos"] = counts.get("repos", 0) + 1

    def _import_forge_links(kind: str, obj_id: int, items: list) -> None:
        for item in items:
            number = int(item.get("number", 0) or 0)
            if number <= 0:
                continue
            try:
                store.link_forge(
                    kind,
                    obj_id,
                    number,
                    provider=str(item.get("provider", "") or "github"),
                    kind=str(item.get("kind", "") or "pull"),
                    url=str(item.get("url", "") or ""),
                    title=str(item.get("title", "") or ""),
                    state=str(item.get("state", "") or ""),
                    checks=str(item.get("checks", "") or ""),
                    reviews=str(item.get("reviews", "") or ""),
                    author=str(item.get("author", "") or ""),
                    base_ref=str(item.get("base_ref", "") or ""),
                    head_ref=str(item.get("head_ref", "") or ""),
                    merged_at=str(item.get("merged_at", "") or ""),
                    merge_commit_sha=str(item.get("merge_commit_sha", "") or ""),
                    updated_at=int(item.get("updated_at", 0) or 0),
                    stale=bool(item.get("stale", False)),
                    payload=str(item.get("payload", "") or ""),
                    actor=actor,
                )
            except (ValueError, KeyError):
                continue
            counts["forge_links"] += 1

    def _import_notes(kind: str, obj_id: int, items: list) -> None:
        for item in items:
            if not isinstance(item, dict):
                continue
            restored = store.restore_note(
                kind,
                obj_id,
                str(item.get("text", "") or ""),
                str(item.get("actor", "") or "human"),
                float(item.get("ts", 0) or 0),
            )
            if restored is not None:
                counts["notes"] += 1

    def _import_comments(kind: str, obj_id: int, items: list) -> None:
        for item in items:
            if not isinstance(item, dict):
                continue
            comment = store.restore_comment(
                kind,
                obj_id,
                str(item.get("text", "") or ""),
                str(item.get("actor", "") or "human"),
                float(item.get("ts", 0) or 0),
                bool(item.get("resolved", False)),
            )
            if comment is not None:
                counts["comments"] += 1

    def _import_issues(kind: str, obj_id: int, items: list) -> None:
        for item in items:
            if not isinstance(item, dict):
                continue
            provider = str(item.get("provider", "") or "")
            external_id = str(item.get("external_id", "") or "")
            if not provider or not external_id:
                continue
            try:
                store.add_issue_link(
                    provider,
                    external_id,
                    str(item.get("number", "") or ""),
                    str(item.get("url", "") or ""),
                    str(item.get("title", "") or ""),
                    str(item.get("state", "") or ""),
                    kind,
                    obj_id,
                    float(item.get("updated_at", 0) or 0),
                )
            except Exception:
                continue
            counts["issues"] += 1

    def _import_claim(task_id: int, item: object) -> None:
        if not isinstance(item, dict):
            return
        try:
            restored = store.restore_claim(
                task_id,
                str(item.get("actor", "") or "human"),
                float(item.get("started_at", 0) or 0),
                float(item.get("expires_at", 0) or 0),
                float(item.get("renewed_at", 0) or 0),
                str(item.get("note", "") or ""),
            )
        except (ValueError, TypeError):
            return
        if restored:
            counts["claims"] += 1

    for entry in data.get("plans", []):
        p = entry["plan"]
        np = store.add_plan(
            p.get("name", p.get("title", "imported")),
            p.get("description", ""),
            goal=p.get("goal", ""),
            actor=actor,
        )
        _apply_status("plan", np.id, p.get("status", ""))
        uid = str(p.get("uid", "") or "").strip()
        if uid and store.get_plan_by_uid(uid) is None:
            store.set_plan_uid(np.id, uid)
        counts["plans"] += 1
        _import_criteria("plan", np.id, entry.get("criteria", []))
        _import_notes("plan", np.id, entry.get("notes", []))
        _import_comments("plan", np.id, entry.get("comments", []))
        _import_issues("plan", np.id, entry.get("issues", []))
        _import_links("plan", np.id, entry.get("links", []))
        _import_forge_links("plan", np.id, entry.get("forge_links", []))
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
            _import_notes("milestone", ns.id, sentry.get("notes", []))
            _import_comments("milestone", ns.id, sentry.get("comments", []))
            _import_issues("milestone", ns.id, sentry.get("issues", []))
            _import_links("milestone", ns.id, sentry.get("links", []))
            _import_forge_links("milestone", ns.id, sentry.get("forge_links", []))
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
                if tp.get("blocked"):
                    store.set_blocked(
                        nt.id,
                        True,
                        str(tp.get("blocked_reason", "") or "blocked (imported)"),
                        actor=actor,
                    )
                counts["tasks"] += 1
                tasks_map[int(tp.get("id", 0) or 0)] = nt.id
                _import_criteria("task", nt.id, tentry.get("criteria", []))
                _import_notes("task", nt.id, tentry.get("notes", []))
                _import_comments("task", nt.id, tentry.get("comments", []))
                _import_issues("task", nt.id, tentry.get("issues", []))
                _import_links("task", nt.id, tentry.get("links", []))
                _import_forge_links("task", nt.id, tentry.get("forge_links", []))
                _import_repos("task", nt.id, tentry.get("repos", []))
                _import_claim(nt.id, tentry.get("claim"))
        # Milestones landed after the plan's own status: recompute it.
        heal(store, "plan", np.id, actor)
    for link in data.get("criterion_links", []):
        if not isinstance(link, dict):
            continue
        cid = criteria_map.get(int(link.get("criterion_id", 0) or 0))
        tid = tasks_map.get(int(link.get("task_id", 0) or 0))
        if cid is None or tid is None:
            continue
        try:
            store.relate_criterion(cid, tid, actor=actor)
        except (KeyError, ValueError):
            continue
        counts["criterion_links"] += 1
    for criterion_id, row in evidence_items:
        old_task = int(row.get("task_id", 0) or 0)
        task_id = tasks_map.get(old_task) if old_task else None
        restored = store.restore_evidence(
            criterion_id,
            task_id=task_id,
            command=str(row.get("command", "") or ""),
            exit_code=row.get("exit_code"),
            commit_sha=str(row.get("commit_sha", "") or ""),
            pr_url=str(row.get("pr_url", "") or ""),
            artifact_path=str(row.get("artifact_path", "") or ""),
            note=str(row.get("note", "") or ""),
            actor=str(row.get("actor", "") or "human"),
            ts=float(row.get("ts", 0) or 0),
        )
        if restored is not None:
            counts["evidence"] += 1
    return counts


def share_render(port: TransferPort, plan_id: int, fmt: str, dest: str | None) -> str | None:
    """Render a read-only share document."""
    from lazyplan.services.share import write

    return write(port, plan_id, fmt, dest)


def sync_plans(port: TransferPort, data: dict, actor: str = "human", dry_run: bool = False) -> dict:
    """Merge a plan dump by stable uid."""
    from lazyplan.services.sync import sync

    return sync(port, data, actor=actor, dry_run=dry_run)


def seed_demo(port: TransferPort) -> None:
    """Insert the demo plan when the store is empty."""
    from lazyplan.services.seed import seed

    seed(port)


def parse_github_issues(data: object) -> list:
    """Normalize a GitHub issue response."""
    from lazyplan.services.issues import parse_github

    return parse_github(data)


def parse_linear_issues(data: object) -> list:
    """Normalize a Linear issue export."""
    from lazyplan.services.issues import parse_linear

    return parse_linear(data)


def import_issues(
    port: TransferPort,
    issues: list,
    actor: str = "human",
    as_kind: str = "plan",
    milestone: int = 0,
    dry_run: bool = False,
) -> dict:
    """Create rows from normalized issues or refresh source metadata."""
    from lazyplan.services.issues import import_issues as _import_issues

    return _import_issues(
        port, issues, actor=actor, as_kind=as_kind, milestone=milestone, dry_run=dry_run
    )
