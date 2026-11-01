"""Pure detail document builder for the read view."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from ...design import escape_markup, status_word
from ...render import render_commits, render_forge_links
from ...source import SourceTrail, build_source_trail
from ...store import Store
from ...vcs import commit_url, detect_backend, origin_url

KIND_KEYS = {"plan": "plan", "milestone": "milestone", "task": "task"}


@dataclass(frozen=True)
class DetailDocument:
    """The detail header and read body."""

    head: str
    body: str


def detail_object(full: dict[str, Any], kind: str) -> dict[str, Any]:
    return dict(full.get(KIND_KEYS[kind], {}))


def detail_breadcrumb(store: Store, kind: str, oid: int, obj: dict[str, Any]) -> str:
    if kind == "plan":
        return f"P{oid}"
    if kind == "milestone":
        return f"P{obj.get('plan_id')} › M{oid}"
    milestone = store.get_milestone(int(obj.get("milestone_id", 0)))
    plan_id = milestone.plan_id if milestone else "?"
    return f"P{plan_id} › M{obj.get('milestone_id')} › T{oid}"


def _read_text(lines: list[str], kind: str, obj: dict[str, Any]) -> None:
    desc = str(obj.get("description", "") or "").strip()
    goal = str(obj.get("goal", "") or "").strip() if kind == "plan" else ""
    if goal:
        lines.extend(["", "[bold dim]why[/]", goal])
    if desc:
        heading = "[bold dim]what[/]" if kind == "plan" else "[bold dim]details[/]"
        lines.extend(["", heading, desc])


def _read_coordination(lines: list[str], full: dict[str, Any], obj: dict[str, Any]) -> None:
    if obj.get("blocked"):
        reason = str(obj.get("blocked_reason", "") or "").strip()
        lines.append(f"\n[red]blocked[/] {escape_markup(reason) if reason else ''}".rstrip())
    gate = obj.get("gate")
    if gate:
        lines.append(
            f"\n[dim]gate[/] {escape_markup(str(gate.get('state')))} · {gate.get('prs', 0)} PRs"
        )
    claim = obj.get("claim")
    if claim:
        expires = int(float(claim.get("expires_at") or 0))
        state = "expired" if expires and expires <= int(time.time()) else "active"
        lines.append(f"\n[dim]claim[/] @{escape_markup(str(claim.get('actor', '')))} ({state})")
    comments = [
        comment
        for comment in (full.get("comments") or obj.get("comments") or [])
        if not comment.get("resolved")
    ]
    if comments:
        lines.extend(["", f"[dim]comments {len(comments)}[/]"])
        for comment in comments[-3:]:
            lines.append(
                f"  [dim]@{escape_markup(str(comment.get('actor', '')))}[/] "
                f"{escape_markup(str(comment.get('text', '')))}"
            )
    notes = full.get("notes") or obj.get("notes") or []
    if notes:
        lines.extend(["", f"[dim]notes {len(notes)}[/]"])
        for note in notes[-3:]:
            lines.append(
                f"  [dim]@{escape_markup(str(note.get('actor', '')))}[/] "
                f"{escape_markup(str(note.get('text', '')))}"
            )


def _read_criteria(lines: list[str], full: dict[str, Any]) -> None:
    criteria = full.get("criteria", [])
    if not criteria:
        return
    done = sum(1 for criterion in criteria if criterion.get("done"))
    lines.extend(["", f"[bold dim]acceptance {done}/{len(criteria)}[/]"])
    for criterion in criteria:
        mark = "●" if criterion.get("done") else "○"
        lines.append(f"  {mark} {escape_markup(str(criterion.get('text', '')))}")


def _read_children(lines: list[str], kind: str, full: dict[str, Any]) -> None:
    if kind == "plan":
        milestones = full.get("milestones", [])
        if not milestones:
            return
        lines.extend(["", f"[bold dim]milestones {len(milestones)}[/]"])
        for entry in milestones:
            milestone = entry["milestone"]
            tasks = entry.get("tasks", [])
            tasks_done = sum(1 for task in tasks if task.get("status") == "done")
            lines.append(
                f"  {status_word(str(milestone.get('status', '')), 'rich')} "
                f"[dim]M{milestone.get('id')}[/] "
                f"{escape_markup(str(milestone.get('title', '')))} "
                f"[dim]{tasks_done}/{len(tasks)}[/]"
            )
        return
    if kind != "milestone":
        return
    tasks = [entry.get("task", {}) for entry in full.get("tasks", [])]
    if not tasks:
        return
    lines.extend(["", f"[bold dim]tasks {len(tasks)}[/]"])
    for task in tasks:
        lines.append(
            f"  {status_word(str(task.get('status', '')), 'rich')} "
            f"[dim]T{task.get('id')}[/] {escape_markup(str(task.get('title', '')))}"
        )


def _remote_urls(full: dict[str, Any], links: list[dict[str, Any]]) -> dict[str, str]:
    stored = {
        str(repo.get("repo_path", "") or ""): str(repo.get("repo_remote", "") or "")
        for repo in full.get("effective_repos") or full.get("repos") or []
    }
    cache: dict[str, str] = {}
    for link in links:
        repo = str(link.get("repo_root", "") or "")
        if not repo or repo in cache:
            continue
        remote = stored.get(repo, "")
        if not remote:
            backend, root = detect_backend(repo)
            if backend is not None and root is not None:
                remote = origin_url(backend, root)
        cache[repo] = remote
    return cache


def _read_git(lines: list[str], trail: SourceTrail | None) -> None:
    rows: list[str] = []
    for repo in trail.repos if trail is not None else ():
        branch = repo.branch or ("detached" if repo.detached else "unknown")
        state = "dirty" if repo.dirty else "clean"
        tracking = f"{repo.ahead} ahead, {repo.behind} behind" if repo.branch else "no upstream"
        rows.append(f"  {escape_markup(repo.name or repo.path)} · {branch} · {state} · {tracking}")
    if rows:
        lines.extend(["", "[bold dim]git[/]", *rows])


def _read_forge(lines: list[str], full: dict[str, Any]) -> None:
    links = full.get("effective_forge_links") or full.get("forge_links") or []
    if not links:
        return
    lines.extend(["", "[bold dim]pull requests[/]"])
    for line in render_forge_links(links).splitlines():
        lines.append(f"  {escape_markup(line)}")


def _read_source(
    lines: list[str],
    store: Store,
    kind: str,
    oid: int,
    trail: SourceTrail | None,
) -> None:
    trail = trail or build_source_trail(store, kind, oid)
    if trail.empty:
        lines.extend(
            [
                "",
                "[bold dim]source[/]",
                "  [dim]no linked commits or PRs · link a commit or run task finish[/]",
            ]
        )
        return
    summary = f"{trail.commit_count} commits · {trail.file_count} files · {trail.pull_count} PRs"
    if trail.stale_count:
        summary += f" · {trail.stale_count} stale"
    lines.extend(["", f"[bold dim]source · {summary}[/]"])
    for repo in trail.repos[:3]:
        state = "dirty" if repo.dirty else "clean"
        branch = repo.branch or ("detached" if repo.detached else "unknown")
        lines.append(
            f"  [bold]{escape_markup(repo.name)}[/] · "
            f"{escape_markup(branch)} · {state} · "
            f"{len(repo.commits)}c · {len(repo.pulls)}PR"
        )
        for commit in repo.commits[:2]:
            files = f" · {len(commit.files)} files" if commit.files else ""
            stale = " · stale" if commit.stale else ""
            lines.append(
                f"    [dim]{commit.short}[/] "
                f"{escape_markup(commit.subject or '(no subject)')}[dim]{files}{stale}[/]"
            )
        if repo.error:
            lines.append(f"    [red]{escape_markup(repo.error)}[/]")
    if len(trail.repos) > 3:
        lines.append(f"  [dim]+{len(trail.repos) - 3} more repos[/]")
    lines.append("  [dim]g source trail[/]")


def _read_links(lines: list[str], full: dict[str, Any]) -> None:
    links = full.get("effective_links") or full.get("links") or []
    if links:
        remotes = _remote_urls(full, links)
        lines.extend(["", "[bold dim]commits[/]"])
        for link in links:
            text = render_commits([link])
            url = commit_url(
                remotes.get(str(link.get("repo_root", "") or ""), ""),
                str(link.get("sha", "")),
            )
            suffix = f" [dim]{escape_markup(url)}[/]" if url else ""
            lines.append(f"  {escape_markup(text)}{suffix}")
    repos = full.get("effective_repos") or full.get("repos") or []
    if not repos:
        return
    lines.extend(["", "[bold dim]repos[/]"])
    for repo in repos:
        path = str(repo.get("repo_path", ""))
        remote = str(repo.get("repo_remote", "") or "")
        branch = str(repo.get("branch", "") or "")
        lines.append(
            f"  {path}" + (f" ({remote})" if remote else "") + (f" · {branch}" if branch else "")
        )


def build_detail(
    store: Store,
    kind: str,
    oid: int,
    full: dict[str, Any],
    trail: SourceTrail | None,
) -> DetailDocument:
    """Build the read view for one plan, milestone, or task."""
    obj = detail_object(full, kind)
    title = str(obj.get("title", obj.get("name", "")))
    status = str(obj.get("status", ""))
    pill = f" [reverse] {status.upper()} [/]" if status else ""
    lines = [f"{status_word(status, 'rich')} [bold]{escape_markup(title)}[/]{pill}"]
    head = f"[bold]DETAIL[/] [dim]· {detail_breadcrumb(store, kind, oid, obj)}[/]"
    _read_text(lines, kind, obj)
    _read_coordination(lines, full, obj)
    _read_criteria(lines, full)
    _read_children(lines, kind, full)
    _read_forge(lines, full)
    _read_source(lines, store, kind, oid, trail)
    _read_git(lines, trail)
    _read_links(lines, full)
    return DetailDocument(head=head, body="\n".join(lines))
