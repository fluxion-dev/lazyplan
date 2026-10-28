"""Rows CLI commands."""

from __future__ import annotations

import argparse

from .. import (
    porcelain,
    services,
)
from ..models import Status
from ..render import (
    summary_lines,
    tree_lines,
)
from ..store import Store, to_payload
from .emit import (
    _porcelain_row,
    _progress,
    _tty_dot,
)


def _list_filters(args: argparse.Namespace) -> tuple[str, Status | None]:
    """Translate --archived/--status into service filters."""
    if args.archived:
        return "only", None
    if args.status is None:
        return "hide", None
    if args.status == "all":
        return "show", None
    return "hide", Status(args.status)


def _list_limit(args: argparse.Namespace) -> int | None:
    """Default text lists cap plans; explicit rows, --all, and JSON do not."""
    if args.plan is not None or args.all:
        return None
    if args.json:
        return int(args.limit) if args.limit is not None else None
    return int(args.limit) if args.limit is not None else services.DEFAULT_PLAN_LIMIT


def _list_payload(
    store: Store,
    status: Status | None,
    archived: str,
    limit: int | None,
    repo: str | None,
    milestone: int | None,
    plan_id: int | None,
) -> list[dict]:
    """Full JSON tree; shape stays stable for scripts."""
    criteria = store.criteria_map()
    links = store.vcs_links_map()
    repos = store.repos_map()
    payload = []
    for plan, milestones in services.tree(
        store,
        status=status,
        plan_id=plan_id,
        archived=archived,
        limit=limit,
        repo=repo,
        milestone_id=milestone,
    ):
        plan_repos = repos.get(("plan", plan.id), [])
        milestone_rows = []
        for ms, tasks in milestones:
            milestone_repos = repos.get(("milestone", ms.id), []) or plan_repos
            task_rows = []
            for task in tasks:
                task_rows.append(
                    {
                        "task": to_payload(vars(task)),
                        "criteria": [vars(item) for item in criteria.get(("task", task.id), [])],
                        "links": [vars(item) for item in links.get(("task", task.id), [])],
                        "repos": repos.get(("task", task.id), []),
                        "effective_repos": repos.get(("task", task.id), []) or milestone_repos,
                    }
                )
            milestone_rows.append(
                {
                    "milestone": to_payload(vars(ms)),
                    "criteria": [vars(item) for item in criteria.get(("milestone", ms.id), [])],
                    "links": [vars(item) for item in links.get(("milestone", ms.id), [])],
                    "repos": repos.get(("milestone", ms.id), []),
                    "effective_repos": milestone_repos,
                    "tasks": task_rows,
                }
            )
        payload.append(
            {
                "plan": to_payload(vars(plan)),
                "criteria": [vars(item) for item in criteria.get(("plan", plan.id), [])],
                "links": [vars(item) for item in links.get(("plan", plan.id), [])],
                "repos": plan_repos,
                "effective_repos": plan_repos,
                "milestones": milestone_rows,
            }
        )
    return payload


def _list_lines(
    store: Store,
    args: argparse.Namespace,
    status: Status | None,
    archived: str,
    limit: int | None,
    repo: str | None,
    milestone: int | None,
) -> list[str]:
    """Summary by default; --tree (or a milestone filter) shows hierarchy."""
    dot = _tty_dot(args)
    if getattr(args, "tree", False) or milestone is not None:
        return tree_lines(
            store,
            status,
            args.plan,
            dot=dot,
            archived=archived,
            limit=limit,
            repo=repo,
            milestone_id=milestone,
        )
    return summary_lines(
        store,
        status,
        args.plan,
        dot=dot,
        archived=archived,
        limit=limit,
        repo=repo,
    )


def _porcelain_list_lines(
    store: Store,
    status: Status | None,
    plan_id: int | None,
    archived: str,
    limit: int | None,
    repo: str | None,
    milestone_id: int | None,
    tree: bool,
) -> list[str]:
    """Plan rows for a summary; plan, milestone, and task rows for a tree."""
    lines: list[str] = []
    for plan, milestones in services.tree(
        store,
        status=status,
        plan_id=plan_id,
        archived=archived,
        limit=limit,
        repo=repo,
        milestone_id=milestone_id,
    ):
        lines.append(_porcelain_row(store, plan))
        if not tree:
            continue
        for milestone, tasks in milestones:
            lines.append(_porcelain_row(store, milestone))
            lines.extend(_porcelain_row(store, task) for task in tasks)
    return lines


def _note_dict_rows(items: list[dict]) -> list[str]:
    """Note rows from show/brief payload dicts."""
    return [
        porcelain.note_row(
            note["id"],
            note.get("actor"),
            note.get("text"),
            note.get("parent_kind", "note"),
            note.get("parent_id", "-"),
            note.get("ts", 0),
        )
        for note in items
    ]


def _gate_row(gate: dict | None) -> list[str]:
    """Porcelain gate row when a task has linked PRs."""
    if not gate:
        return []
    return [
        porcelain.row(
            "gate",
            gate.get("state"),
            gate.get("checks"),
            f"{gate.get('prs', 0)} PRs",
            "-",
            "-",
        )
    ]


def _issue_dict_rows(items: list[dict]) -> list[str]:
    """Porcelain issue-source rows."""
    return [
        porcelain.row(
            "issue",
            item.get("number") or item.get("external_id"),
            item.get("state"),
            item.get("title"),
            f"{item.get('provider')}:{item.get('external_id')}",
            item.get("url") or "-",
        )
        for item in items
    ]


def _comment_dict_rows(items: list[dict]) -> list[str]:
    """Comment rows from show/brief payload dicts."""
    return [
        porcelain.comment_row(
            item["id"],
            item.get("actor"),
            item.get("text"),
            item.get("parent_kind", "comment"),
            item.get("parent_id", "-"),
            item.get("ts", 0),
            bool(item.get("resolved")),
        )
        for item in items
    ]


def _claim_line(store: Store, task_id: int, title: str) -> str | None:
    """Claim row for a task, or None when it has no lease."""
    claim = store.get_claim(task_id)
    if claim is None:
        return None
    return porcelain.claim_row(task_id, claim.actor, title, claim.expires_at)


def _porcelain_show_lines(store: Store, kind: str, full: dict) -> list[str]:
    """Plain definition rows plus criteria and children; no repo or commit noise."""
    lines: list[str] = []
    if kind == "plan":
        plan = full["plan"]
        lines.append(
            porcelain.plan_row(
                plan["id"], plan["status"], plan["name"], _progress(store, plan_id=plan["id"])
            )
        )
        lines.append(porcelain.text_row("why", plan.get("goal")))
        lines.append(porcelain.text_row("what", plan.get("description")))
        lines.extend(_criterion_dict_rows(full.get("criteria", [])))
        lines.extend(_note_dict_rows(full.get("notes", [])))
        lines.extend(_comment_dict_rows(full.get("comments", [])))
        lines.extend(_issue_dict_rows(full.get("issues", [])))
        for entry in full.get("milestones", []):
            milestone = entry["milestone"]
            lines.append(
                porcelain.milestone_row(
                    milestone["id"],
                    milestone["status"],
                    milestone["title"],
                    milestone["plan_id"],
                    _progress(store, milestone_id=milestone["id"]),
                )
            )
            lines.extend(_criterion_dict_rows(entry.get("criteria", [])))
            for task in entry.get("tasks", []):
                lines.append(
                    porcelain.task_row(
                        task["id"],
                        task["status"],
                        task["title"],
                        task["milestone_id"],
                        "blocked" if task.get("blocked") else "-",
                    )
                )
                claim_line = _claim_line(store, int(task["id"]), str(task["title"]))
                if claim_line is not None:
                    lines.append(claim_line)
                lines.extend(_gate_row(task.get("gate")))
                lines.extend(_note_dict_rows(task.get("notes", [])))
                lines.extend(_comment_dict_rows(task.get("comments", [])))
                lines.extend(_issue_dict_rows(task.get("issues", [])))
        return lines
    if kind == "milestone":
        milestone = full["milestone"]
        lines.append(
            porcelain.milestone_row(
                milestone["id"],
                milestone["status"],
                milestone["title"],
                milestone["plan_id"],
                _progress(store, milestone_id=milestone["id"]),
            )
        )
        lines.append(porcelain.text_row("desc", milestone.get("description")))
        lines.extend(_criterion_dict_rows(full.get("criteria", [])))
        lines.extend(_note_dict_rows(full.get("notes", [])))
        lines.extend(_comment_dict_rows(full.get("comments", [])))
        lines.extend(_issue_dict_rows(full.get("issues", [])))
        for entry in full.get("tasks", []):
            task = entry["task"]
            lines.append(
                porcelain.task_row(
                    task["id"],
                    task["status"],
                    task["title"],
                    task["milestone_id"],
                    "blocked" if task.get("blocked") else "-",
                )
            )
            claim_line = _claim_line(store, int(task["id"]), str(task["title"]))
            if claim_line is not None:
                lines.append(claim_line)
            lines.extend(_gate_row(task.get("gate")))
            lines.extend(_note_dict_rows(task.get("notes", [])))
            lines.extend(_comment_dict_rows(task.get("comments", [])))
            lines.extend(_issue_dict_rows(task.get("issues", [])))
        return lines
    task = full["task"]
    lines.append(
        porcelain.task_row(
            task["id"],
            task["status"],
            task["title"],
            task["milestone_id"],
            "blocked" if task.get("blocked") else "-",
        )
    )
    claim_line = _claim_line(store, int(task["id"]), str(task["title"]))
    if claim_line is not None:
        lines.append(claim_line)
    lines.extend(_gate_row(task.get("gate")))
    lines.append(porcelain.text_row("desc", task.get("description")))
    lines.extend(_criterion_dict_rows(full.get("criteria", [])))
    lines.extend(_note_dict_rows(task.get("notes", [])))
    lines.extend(_comment_dict_rows(task.get("comments", [])))
    lines.extend(_issue_dict_rows(task.get("issues", [])))
    return lines


def _criterion_dict_rows(items: list[dict]) -> list[str]:
    """Criterion rows from `show` or `brief` payload dicts."""
    return [
        porcelain.row(
            "criterion",
            item["id"],
            "done" if item.get("done") else "open",
            item.get("text"),
            f"{item.get('parent_kind', item.get('kind'))}:{item.get('parent_id', item.get('id'))}",
            "-",
        )
        for item in items
    ]
