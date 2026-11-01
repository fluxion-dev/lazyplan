"""Pure detail document builder for the read view."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from ...design import SECTION_ICON, escape_markup, status_word
from ...render import render_forge_links
from ...source import SourceTrail, build_source_trail
from ...store import Store

KIND_KEYS = {"plan": "plan", "milestone": "milestone", "task": "task"}


def _heading(key: str, label: str) -> str:
    """One section heading with its icon."""
    icon = SECTION_ICON.get(key, "")
    return f"[bold cyan]{icon}[/] [bold]{label}[/]" if icon else f"[bold]{label}[/]"


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
        lines.extend(["", _heading("why", "why"), goal])
    if desc:
        key = "what" if kind == "plan" else "details"
        heading = "what" if kind == "plan" else "details"
        lines.extend(["", _heading(key, heading), desc])


def _read_coordination(lines: list[str], full: dict[str, Any], obj: dict[str, Any]) -> None:
    if obj.get("blocked"):
        reason = str(obj.get("blocked_reason", "") or "").strip()
        lines.append(f"\n[red]⚑ blocked[/] {escape_markup(reason) if reason else ''}".rstrip())
    gate = obj.get("gate")
    if gate:
        lines.append(
            f"\n[dim]⚑ gate[/] {escape_markup(str(gate.get('state')))} · {gate.get('prs', 0)} PRs"
        )
    claim = obj.get("claim")
    if claim:
        expires = int(float(claim.get("expires_at") or 0))
        state = "expired" if expires and expires <= int(time.time()) else "active"
        lines.append(f"\n[dim]◉ claim[/] @{escape_markup(str(claim.get('actor', '')))} ({state})")
    comments = [
        comment
        for comment in (full.get("comments") or obj.get("comments") or [])
        if not comment.get("resolved")
    ]
    if comments:
        lines.extend(["", _heading("comments", f"comments {len(comments)}")])
        for comment in comments[-3:]:
            lines.append(
                f"  [dim]@{escape_markup(str(comment.get('actor', '')))}[/] "
                f"{escape_markup(str(comment.get('text', '')))}"
            )
    notes = full.get("notes") or obj.get("notes") or []
    if notes:
        lines.extend(["", _heading("notes", f"notes {len(notes)}")])
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
    lines.extend(["", _heading("acceptance", f"acceptance {done}/{len(criteria)}")])
    for criterion in criteria:
        mark = "[green]●[/]" if criterion.get("done") else "[dim]○[/]"
        lines.append(f"  {mark} {escape_markup(str(criterion.get('text', '')))}")


def _read_children(lines: list[str], kind: str, full: dict[str, Any]) -> None:
    if kind == "plan":
        milestones = full.get("milestones", [])
        if not milestones:
            return
        lines.extend(["", _heading("milestones", f"milestones {len(milestones)}")])
        for entry in milestones:
            milestone = entry["milestone"]
            tasks = entry.get("tasks", [])
            tasks_done = sum(1 for task in tasks if task.get("status") == "done")
            lines.append(
                f"  {status_word(str(milestone.get('status', '')), 'rich')} "
                f"[dim]◇ M{milestone.get('id')}[/] "
                f"{escape_markup(str(milestone.get('title', '')))} "
                f"[dim]{tasks_done}/{len(tasks)}[/]"
            )
        return
    if kind != "milestone":
        return
    tasks = [entry.get("task", {}) for entry in full.get("tasks", [])]
    if not tasks:
        return
    lines.extend(["", _heading("tasks", f"tasks {len(tasks)}")])
    for task in tasks:
        lines.append(
            f"  {status_word(str(task.get('status', '')), 'rich')} "
            f"[dim]▹ T{task.get('id')}[/] {escape_markup(str(task.get('title', '')))}"
        )


def _read_forge(lines: list[str], full: dict[str, Any]) -> None:
    links = full.get("effective_forge_links") or full.get("forge_links") or []
    if not links:
        return
    lines.extend(["", _heading("pulls", "pull requests")])
    for line in render_forge_links(links).splitlines():
        lines.append(f"  [magenta]⇄[/] {escape_markup(line)}")


def _commit_lines(commit: Any) -> list[str]:
    files = f" · {len(commit.files)} files" if commit.files else ""
    stale = " · [red]\\[stale][/]" if commit.stale else ""
    rows = [
        f"    [dim]◆ {commit.short}[/] "
        f"{escape_markup(commit.subject or '(no subject)')}[dim]{files}[/]{stale}"
    ]
    if commit.url:
        rows.append(f"      [dim]{escape_markup(commit.url)}[/]")
    return rows


def _repo_lines(repo: Any) -> list[str]:
    state = "dirty" if repo.dirty else "clean"
    branch = repo.branch or ("detached" if repo.detached else "unknown")
    icon = "●" if repo.dirty else "○"
    tracking = f" · {repo.ahead} ahead, {repo.behind} behind" if repo.branch else ""
    rows = [
        f"  {icon} [bold]{escape_markup(repo.name)}[/] · "
        f"{escape_markup(branch)} · {state}{tracking} · "
        f"{len(repo.commits)}c · {len(repo.pulls)}PR"
    ]
    for commit in repo.commits[:3]:
        rows.extend(_commit_lines(commit))
    if repo.error:
        rows.append(f"    [red]{escape_markup(repo.error)}[/]")
    return rows


def _orphan_lines(links: list[dict[str, Any]]) -> list[str]:
    rows = ["", _heading("git", f"git · source · {len(links)} commits")]
    for link in links[:3]:
        short = str(link.get("sha", ""))[:12]
        subject = escape_markup(str(link.get("subject", "") or "(no subject)"))
        rows.append(f"    [dim]◆ {short}[/] {subject}")
    rows.append("  [dim]g source trail[/]")
    return rows


def _source_lines(trail: SourceTrail, links: list[dict[str, Any]]) -> list[str]:
    if trail.empty:
        if links:
            return _orphan_lines(links)
        return [
            "",
            _heading("git", "git · source"),
            "  [dim]no linked commits or PRs · link a commit or run task finish[/]",
        ]
    summary = f"{trail.commit_count} commits · {trail.file_count} files · {trail.pull_count} PRs"
    if trail.stale_count:
        summary += f" · {trail.stale_count} stale"
    rows = ["", _heading("git", f"git · source · {summary}")]
    for repo in trail.repos[:3]:
        rows.extend(_repo_lines(repo))
    if len(trail.repos) > 3:
        rows.append(f"  [dim]+{len(trail.repos) - 3} more repos[/]")
    rows.append("  [dim]g source trail[/]")
    return rows


def _read_source(
    lines: list[str],
    store: Store,
    kind: str,
    oid: int,
    full: dict[str, Any],
    trail: SourceTrail | None,
) -> None:
    trail = trail or build_source_trail(store, kind, oid)
    links = full.get("effective_links") or full.get("links") or []
    lines.extend(_source_lines(trail, links))


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
    head = (
        f"{status_word(status, 'rich')} [bold]{escape_markup(title)}[/]{pill}\n"
        f"[dim]{detail_breadcrumb(store, kind, oid, obj)}[/]"
    )
    lines: list[str] = []
    _read_text(lines, kind, obj)
    _read_coordination(lines, full, obj)
    _read_criteria(lines, full)
    _read_children(lines, kind, full)
    _read_forge(lines, full)
    _read_source(lines, store, kind, oid, full, trail)
    return DetailDocument(head=head, body="\n".join(lines).lstrip("\n"))
