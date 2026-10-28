"""Proof, feed, and report rows for the CLI."""

from __future__ import annotations

import time

from .. import audit, porcelain
from ..store import Store
from .emit import _porcelain_row
from .rows import (
    _claim_line,
    _comment_dict_rows,
    _criterion_dict_rows,
    _gate_row,
    _issue_dict_rows,
    _note_dict_rows,
)


def _commit_row(link: dict, parent: str) -> str:
    """One commit record; the full SHA stays the id."""
    return porcelain.row(
        "commit",
        link.get("sha"),
        "stale" if link.get("stale") else "linked",
        link.get("subject"),
        parent,
        link.get("repo_root") or "-",
    )


def _repo_row(row: dict, parent: str, status: str) -> str:
    """One repo link; title carries the remote and extra the branch."""
    return porcelain.row(
        "repo",
        row.get("repo_path"),
        status,
        row.get("repo_remote") or "-",
        parent,
        row.get("branch") or "-",
    )


def _feed_row(event: dict) -> str:
    """One feed event: id, actor, detail, event kind/action, and timestamp."""
    return porcelain.row(
        "feed",
        event.get("id"),
        event.get("actor"),
        event.get("detail"),
        f"{event.get('kind')}/{event.get('action')}",
        int(float(event.get("ts") or 0)),
    )


def _info_rows(payload: dict) -> list[str]:
    """`info` as key/value rows, including each count."""
    rows = [
        porcelain.row("info", "db", "-", payload.get("db"), "-", "-"),
        porcelain.row("info", "repo", "-", payload.get("repo"), "-", "-"),
        porcelain.row("info", "scope", "-", payload.get("scope"), "-", "-"),
        porcelain.row(
            "info",
            "plan_files",
            "-",
            ",".join(str(name) for name in payload.get("plan_files", [])),
            "-",
            "-",
        ),
    ]
    for key, value in (payload.get("counts") or {}).items():
        rows.append(porcelain.row("info", key, "-", value, "-", "-"))
    return rows


def _audit_rows(report: audit.Report) -> list[str]:
    """Audit metrics plus every open gap."""
    window = (
        "all history"
        if not report.since
        else time.strftime("%Y-%m-%d %H:%M", time.localtime(report.since))
    )
    rows = [
        porcelain.row("metric", "plans", "-", ",".join(f"P{plan}" for plan in report.plans)),
        porcelain.row("metric", "since", "-", window),
        porcelain.row("metric", "repos", "-", len(report.repos)),
        porcelain.row("metric", "commits_total", "-", report.commits_total),
        porcelain.row("metric", "commits_linked", "-", report.commits_linked),
        porcelain.row("metric", "coverage", "-", round(report.coverage, 4)),
        porcelain.row("metric", "median_lag_commits", "-", report.median_lag_commits),
        porcelain.row("metric", "median_lag_minutes", "-", report.median_lag_minutes),
        porcelain.row("metric", "unresolved_lag", "-", report.unresolved),
        porcelain.row("metric", "gaps", "-", len(report.gaps)),
        porcelain.row("metric", "criteria_total", "-", report.criteria_total),
        porcelain.row("metric", "criteria_linked", "-", report.criteria_linked),
        porcelain.row("metric", "trace_coverage", "-", round(report.trace_coverage, 4)),
        porcelain.row("metric", "trace_gaps", "-", len(report.trace_gaps)),
    ]
    rows.extend(porcelain.row("gap", f"{gap.kind}:{gap.id}", "-", gap.text) for gap in report.gaps)
    rows.extend(
        porcelain.row("gap", f"{gap.kind}:{gap.id}", "-", gap.text) for gap in report.trace_gaps
    )
    return rows


def _brief_rows(store: Store, payload: dict) -> list[str]:
    """Brief as plan, doing, next, criterion, and unlinked commit rows."""
    rows = [porcelain.row("metric", "active", "-", payload.get("active", 0))]
    for entry in payload.get("plans", []):
        plan = store.get_plan(int(entry["id"]))
        if plan is not None:
            rows.append(_porcelain_row(store, plan))
        rows.extend(_note_dict_rows(entry.get("notes", [])))
        rows.extend(_comment_dict_rows(entry.get("comments", [])))
        for task in entry.get("doing", []):
            model = store.get_task(int(task["id"]))
            if model is not None:
                rows.append(_porcelain_row(store, model))
                claim_line = _claim_line(store, int(task["id"]), str(task["title"]))
                if claim_line is not None:
                    rows.append(claim_line)
                rows.extend(_gate_row(task.get("gate")))
                rows.extend(_note_dict_rows(task.get("notes", [])))
                rows.extend(_comment_dict_rows(task.get("comments", [])))
        next_task = entry.get("next")
        if next_task:
            parent = "-"
            model = store.get_task(int(next_task["id"]))
            if model is not None:
                parent = f"milestone:{model.milestone_id}"
            rows.append(
                porcelain.row("next", next_task["id"], "-", next_task["title"], parent, "-")
            )
        rows.extend(_criterion_dict_rows(entry.get("criteria", [])))
        for commit in entry.get("unlinked", []):
            rows.append(
                porcelain.row(
                    "commit",
                    commit.get("sha"),
                    "unlinked",
                    commit.get("subject"),
                    f"plan:{entry['id']}",
                    int(float(commit.get("timestamp") or 0)),
                )
            )
    return rows


def _git_status_rows(entries: list[dict], parent: str) -> list[str]:
    """One row per checkout with branch, dirty state, and tracking facts."""
    rows: list[str] = []
    for entry in entries:
        path = entry.get("repo_path")
        if entry.get("error"):
            rows.append(
                porcelain.row(
                    "status", path, "error", entry["error"], parent, entry.get("repo_remote")
                )
            )
            continue
        branch = entry.get("branch") or ("detached" if entry.get("detached") else "unknown")
        head = str(entry.get("head") or "")[:12]
        extra = (
            f"head={head or '-'} ahead={entry.get('ahead', 0)} behind={entry.get('behind', 0)} "
            f"upstream={entry.get('upstream') or '-'} subject={entry.get('subject') or '-'}"
        )
        rows.append(
            porcelain.row(
                "status",
                path,
                "dirty" if entry.get("dirty") else "clean",
                branch,
                parent,
                extra,
            )
        )
    return rows


def _pr_row(link: dict, parent: str) -> str:
    """One pull request; title is the PR title and extra is the URL."""
    return porcelain.row(
        "pr",
        link.get("number"),
        link.get("state") or "unknown",
        link.get("title") or "-",
        parent,
        link.get("url") or "-",
    )


def _pr_status_rows(entries: list[dict], parent: str) -> list[str]:
    """One row per checkout with provider, auth source, and cache state."""
    rows: list[str] = []
    for entry in entries:
        path = entry.get("repo_path")
        summary = (
            f"{entry.get('provider', 'github')} auth={entry.get('auth_source') or 'none'} "
            f"cache={entry.get('cache') or 'none'} remote={entry.get('repo_remote') or '-'}"
        )
        if entry.get("error"):
            rows.append(porcelain.row("pr-status", path, "error", entry["error"], parent, summary))
        else:
            rows.append(
                porcelain.row("pr-status", path, "ready", entry.get("slug") or "-", parent, summary)
            )
    return rows


def _scan_row(match: dict) -> str:
    """One git scan match: SHA, action, subject, and the matched row ref."""
    return porcelain.row(
        "scan", match.get("sha"), match.get("action"), match.get("subject"), match.get("ref"), "-"
    )


def _trace_entries(payload: dict) -> list[dict]:
    """Normalize a plan or criterion trace payload to criterion entries."""
    if "criteria" in payload:
        return list(payload["criteria"])
    return [{"criterion": payload["criterion"], "tasks": payload.get("tasks", [])}]


def _trace_text(payload: dict) -> list[str]:
    """Human trace: criterion, proving tasks, commits, and PRs."""
    lines: list[str] = []
    if "plan" in payload:
        plan = payload["plan"]
        lines.append(f"P{plan['id']} {plan['name']} ({plan['status']})")
    for entry in _trace_entries(payload):
        crit = entry["criterion"]
        state = "done" if crit.get("done") else "open"
        lines.append(
            f"criterion #{crit['id']} [{state}] {crit['text']} "
            f"({crit['parent_kind']} #{crit['parent_id']})"
        )
        tasks = entry.get("tasks", [])
        if not tasks:
            lines.append("  (no proving task)")
            continue
        for item in tasks:
            task = item["task"]
            lines.append(f"  T{task['id']} {task['title']} (M{task['milestone_id']})")
            for commit in item.get("commits", []):
                lines.append(f"    {str(commit.get('sha', ''))[:12]} {commit.get('subject', '')}")
            for pull in item.get("forge_links", []):
                lines.append(
                    f"    PR #{pull.get('number')} {pull.get('state') or 'unknown'} "
                    f"{pull.get('title', '')}"
                )
    return lines


def _trace_rows(payload: dict) -> list[str]:
    """Porcelain trace rows: criteria, criterion-task edges, commits, and PRs."""
    rows: list[str] = []
    if "plan" in payload:
        plan = payload["plan"]
        rows.append(porcelain.plan_row(plan["id"], plan["status"], plan["name"]))
    for entry in _trace_entries(payload):
        crit = entry["criterion"]
        rows.append(
            porcelain.row(
                "criterion",
                crit["id"],
                "done" if crit.get("done") else "open",
                crit.get("text"),
                f"{crit['parent_kind']}:{crit['parent_id']}",
                "-",
            )
        )
        tasks = entry.get("tasks", [])
        if not tasks:
            rows.append(
                porcelain.row(
                    "trace",
                    crit["id"],
                    "missing",
                    "-",
                    f"criterion:{crit['id']}",
                    "-",
                )
            )
        for item in tasks:
            task = item["task"]
            rows.append(
                porcelain.row(
                    "trace",
                    crit["id"],
                    "proves",
                    task.get("title"),
                    f"criterion:{crit['id']}",
                    f"task:{task['id']}",
                )
            )
            rows.extend(_issue_dict_rows(item.get("issues", [])))
            for commit in item.get("commits", []):
                rows.append(_commit_row(commit, f"task:{task['id']}"))
            for pull in item.get("forge_links", []):
                rows.append(_pr_row(pull, f"task:{task['id']}"))
    return rows
