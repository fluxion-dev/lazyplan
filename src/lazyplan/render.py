"""Terminal rendering helpers (labels, tree, show, markdown).

Single source of truth for row grammar lives in design.py; this module
only composes multi-line views for the CLI.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING

from .design import INDENT, milestone_label, plan_label, status_word, task_label
from .services import tree as service_tree

if TYPE_CHECKING:
    from .models import Status
    from .store import Store


def _progress_map(store: Store) -> dict[int, tuple[int, int]]:
    """Task progress per plan, independent of status/limit filters."""
    out: dict[int, tuple[int, int]] = {}
    for plan, milestones in service_tree(store, status=None, archived="show"):
        tasks = [task for _, items in milestones for task in items]
        out[plan.id] = (sum(1 for task in tasks if task.status.value == "done"), len(tasks))
    return out


def summary_lines(
    store: Store,
    status: Status | None,
    plan_id: int | None,
    dot: str = "plain",
    archived: str = "hide",
    limit: int | None = None,
    repo: str | None = None,
) -> list[str]:
    """One scannable line per plan: label + done/total tasks."""
    entries = service_tree(
        store,
        status=status,
        plan_id=plan_id,
        archived=archived,
        limit=limit,
        repo=repo,
    )
    entries.sort(key=lambda entry: entry[0].status.value == "done")
    progress = _progress_map(store)
    lines = []
    for plan, _milestones in entries:
        done, total = progress.get(plan.id, (0, 0))
        lines.append(f"{plan_label(plan, store, dot)} {done}/{total}")
    return lines


def tree_lines(
    store: Store,
    status: Status | None,
    plan_id: int | None,
    dot: str = "plain",
    archived: str = "hide",
    limit: int | None = None,
    repo: str | None = None,
    milestone_id: int | None = None,
) -> list[str]:
    """Indented tree lines using the canonical design labels."""
    lines = []
    for p, milestones in service_tree(
        store,
        status=status,
        plan_id=plan_id,
        archived=archived,
        limit=limit,
        repo=repo,
        milestone_id=milestone_id,
    ):
        lines.append(f"{INDENT[0]}{plan_label(p, store, dot)}")
        for s, tasks in milestones:
            lines.append(f"{INDENT[1]}{milestone_label(s, store, dot)}")
            for t in tasks:
                lines.append(f"{INDENT[2]}{task_label(t, store, dot)}")
    return lines


def _commit_line(link: dict, show_repo: bool) -> str:
    """One commit line: short SHA, subject, author, optional repo, stale."""
    sha = str(link.get("sha", ""))
    short = sha[:12] if len(sha) >= 12 else sha
    subject = str(link.get("subject", "") or "").strip()
    author = str(link.get("author", "") or "").strip()
    extra = f" ({author})" if author and subject else author
    line = f"{short} {subject}{extra}".rstrip() if (subject or extra) else short
    repo = str(link.get("repo_root", "") or "")
    if show_repo and repo:
        line = f"{line} · {Path(repo).name}"
    if link.get("stale"):
        line = f"{line} [stale]"
    return line


def _commit_file_lines(link: dict) -> list[str]:
    """Indented changed-file lines for one commit."""
    paths = [str(path) for path in link.get("files", []) if str(path)]
    lines = [f"  {path}" for path in paths[:8]]
    if len(paths) > 8:
        lines.append(f"  +{len(paths) - 8} more")
    return lines


def render_commits(links: list[dict], files: bool = False) -> str:
    """Human-readable commit list for `lpui commits` and `show` sections."""
    roots = {
        str(link.get("repo_root", "") or "")
        for link in links
        if str(link.get("repo_root", "") or "")
    }
    show_repo = len(roots) > 1
    lines = []
    for link in links:
        lines.append(_commit_line(link, show_repo))
        if files:
            lines.extend(_commit_file_lines(link))
    return "\n".join(lines)


def render_git_status(entries: list[dict]) -> str:
    """Human-readable `lpui git status` output, one block per checkout."""
    lines: list[str] = []
    for entry in entries:
        path = str(entry.get("repo_path", "") or "")
        remote = str(entry.get("repo_remote", "") or "")
        lines.append(f"{path}" + (f" ({remote})" if remote else ""))
        if entry.get("error"):
            lines.append(f"  error: {entry['error']}")
            continue
        branch = str(entry.get("branch", "") or "")
        if not branch:
            branch = "detached" if entry.get("detached") else "unknown"
        state = "dirty" if entry.get("dirty") else "clean"
        if entry.get("upstream"):
            tracking = f"{entry.get('ahead', 0)} ahead, {entry.get('behind', 0)} behind"
        else:
            tracking = "no upstream"
        lines.append(f"  branch {branch} · {state} · {tracking}")
        sha = str(entry.get("head", "") or "")
        if sha:
            subject = str(entry.get("subject", "") or "").strip()
            lines.append(f"  {sha[:12]} {subject}".rstrip())
    return "\n".join(lines)


def render_forge_status(entries: list[dict]) -> str:
    """Human-readable `lpui pr status` output, one block per checkout."""
    lines: list[str] = []
    for entry in entries:
        path = str(entry.get("repo_path", "") or "")
        remote = str(entry.get("repo_remote", "") or "")
        lines.append(f"{path}" + (f" ({remote})" if remote else ""))
        if entry.get("error"):
            lines.append(f"  error: {entry['error']}")
            continue
        source = str(entry.get("auth_source", "") or "none")
        cache = str(entry.get("cache", "") or "none")
        lines.append(
            f"  {entry.get('provider', 'github')} {entry.get('slug', '')}"
            f" · auth {source} · cache {cache}"
        )
    return "\n".join(lines)


def _forge_refs(link: dict) -> str:
    """Branch mapping for one PR, or an empty suffix."""
    base_ref = str(link.get("base_ref", "") or "").strip()
    head_ref = str(link.get("head_ref", "") or "").strip()
    if not (base_ref or head_ref):
        return ""
    return f"· {head_ref or '?'} -> {base_ref or '?'}"


def _forge_detail_parts(link: dict) -> list[str]:
    """Optional display parts for one forge link, in a stable order."""
    parts: list[str] = []
    title = str(link.get("title", "") or "").strip()
    if title:
        parts.append(title)
    for name in ("checks", "reviews"):
        value = str(link.get(name, "") or "")
        if value and value != "none":
            parts.append(f"· {name} {value}")
    refs = _forge_refs(link)
    if refs:
        parts.append(refs)
    merge_sha = str(link.get("merge_commit_sha", "") or "").strip()
    if merge_sha:
        parts.append(f"· merge {merge_sha[:12]}")
    for name in ("author", "url"):
        value = str(link.get(name, "") or "").strip()
        if value:
            parts.append(f"· {value}")
    if link.get("stale"):
        parts.append("[stale]")
    return parts


def render_forge_links(links: list[dict]) -> str:
    """Human-readable pull request/issue list for `pr list` and `show`."""
    lines: list[str] = []
    for link in links:
        number = link.get("number", 0)
        label = "PR" if str(link.get("kind", "pull")) == "pull" else "issue"
        state = str(link.get("state", "") or "unknown")
        parts = _forge_detail_parts(link)
        line = f"{label} #{number} {state}"
        if parts:
            line += f" {' '.join(parts)}"
        lines.append(line)
    return "\n".join(lines)


def _append_claim(lines: list[str], claim: dict | None, indent: str = "") -> None:
    """Append one lease line when a task has a claim."""
    if not claim:
        return
    expires = int(float(claim.get("expires_at") or 0))
    when = time.strftime("%Y-%m-%d %H:%M", time.localtime(expires)) if expires else "unknown"
    lines.append(f"{indent}claim: @{claim.get('actor')} until {when}")


def _append_crit(lines: list[str], items: list[dict]) -> None:
    """Append checklist lines."""
    for c in items:
        box = "x" if c.get("done") else " "
        lines.append(f"  [{box}] {c['text']}")


def _append_commits(lines: list[str], items: list[dict], files: bool = False) -> None:
    """Append linked-commit lines."""
    for line in render_commits(items, files=files).splitlines():
        lines.append(f"  {line}")


def _append_repos(lines: list[str], full: dict) -> None:
    """Append linked-repo lines (effective wins over explicit)."""
    items = full.get("effective_repos") or full.get("repos") or []
    if items:
        lines.append("\nrepos:")
        for r in items:
            path = str(r.get("repo_path", "") or "")
            remote = str(r.get("repo_remote", "") or "")
            lines.append(f"  {path}" + (f" ({remote})" if remote else ""))


def _append_common(lines: list[str], full: dict, files: bool = False) -> None:
    """Shared show sections: acceptance + commits + PRs + repos."""
    if full.get("criteria"):
        lines.append("\nacceptance:")
        _append_crit(lines, full["criteria"])
    links = full.get("effective_links") or full.get("links")
    if links:
        lines.append("\ncommits:")
        _append_commits(lines, links, files=files)
    forge_links = full.get("effective_forge_links") or full.get("forge_links")
    if forge_links:
        lines.append("\npull requests:")
        for line in render_forge_links(forge_links).splitlines():
            lines.append(f"  {line}")
    _append_repos(lines, full)


def _render_plan_full(full: dict, lines: list[str], files: bool = False) -> None:
    """Plan show body."""
    from .design import status_word

    p = full["plan"]
    lines.append(f"{status_word(p['status'])} P{p['id']} {p['name']}")
    if p.get("goal"):
        lines.append(f"why: {p['goal']}")
    if p.get("description"):
        lines.append(f"\nwhat: {p['description']}")
    _append_common(lines, full, files=files)
    for entry in full["milestones"]:
        s = entry["milestone"]
        lines.append(f"\n  {status_word(s['status'])} M{s['id']} {s['title']}")


def _render_milestone_full(full: dict, lines: list[str], files: bool = False) -> None:
    """Milestone show body."""
    from .design import status_word

    s = full["milestone"]
    lines.append(f"{status_word(s['status'])} M{s['id']} {s['title']} (P{s['plan_id']})")
    if s.get("description"):
        lines.append(f"\ndetails: {s['description']}")
    _append_common(lines, full, files=files)
    for entry in full["tasks"]:
        t = entry["task"]
        lines.append(f"\n  {status_word(t['status'])} T{t['id']} {t['title']}")
        _append_claim(lines, t.get("claim"), indent="  ")
        if t.get("description"):
            lines.append(f"  {t['description']}")


def _render_task_full(full: dict, lines: list[str], files: bool = False) -> None:
    """Task show body."""
    from .design import status_word

    t = full["task"]
    lines.append(f"{status_word(t['status'])} T{t['id']} {t['title']} (M{t['milestone_id']})")
    _append_claim(lines, t.get("claim"))
    if t.get("description"):
        lines.append(f"\ndetails: {t['description']}")
    _append_common(lines, full, files=files)


def render_full(kind: str, full: dict, files: bool = False) -> str:
    """Human-readable `lpui show`: why/what + criteria + commits + repos + children."""
    lines: list[str] = []
    if kind == "plan":
        _render_plan_full(full, lines, files=files)
    elif kind == "milestone":
        _render_milestone_full(full, lines, files=files)
    else:
        _render_task_full(full, lines, files=files)
    return "\n".join(lines)


def render_markdown(data: dict) -> str:
    """Human/portable markdown export of the whole db."""
    lines = ["# lazyplan export", ""]
    for entry in data.get("plans", []):
        lines.append(render_plan_markdown(entry))
        lines.append("")
    return "\n".join(lines)


def _md_crit(lines: list[str], items: list[dict], indent: str = "") -> None:
    """Checklist lines with ids + ticks."""
    for c in items:
        box = "x" if c.get("done") else " "
        lines.append(f"{indent}- [{box}] {c['text']}")


def _md_repos(lines: list[str], items: list[dict], indent: str = "") -> None:
    """Repo link lines."""
    for r in items:
        remote = f" ({r['repo_remote']})" if r.get("repo_remote") else ""
        lines.append(f"{indent}- repo: {r.get('repo_path', '')}{remote}")


def _md_task_lines(tentry: dict) -> list[str]:
    """Full-fidelity lines for one task entry."""
    lines: list[str] = []
    t = tentry["task"]
    box = "x" if t["status"] == "done" else " "
    lines.append(f"- [{box}] T{t['id']} {t['title']} ({t['status']})")
    if t.get("description"):
        for dline in str(t["description"]).splitlines():
            lines.append(f"  {dline}")
    for c in tentry.get("criteria", []):
        cbox = "x" if c.get("done") else " "
        lines.append(f"  - [{cbox}] {c['text']}")
    return lines


def _md_milestone_lines(sentry: dict) -> list[str]:
    """Full-fidelity lines for one milestone entry."""
    lines: list[str] = []
    s = sentry["milestone"]
    lines.append(f"\n### {status_word(s['status'])} M{s['id']} {s['title']}")
    if s.get("description"):
        lines.append(str(s["description"]))
    _md_crit(lines, sentry.get("criteria", []))
    _md_repos(lines, sentry.get("repos", []))
    for tentry in sentry.get("tasks", []):
        lines.extend(_md_task_lines(tentry))
    return lines


def render_plan_markdown(entry: dict) -> str:
    """Full-fidelity markdown for ONE plan entry (export_all shape).

    Carries every editable field: status, why/what, criteria
    (with ids + ticks), repos, commits, plus per-milestone/task bodies.
    Stays non-importable by design; JSON remains the round-trip format.
    """
    lines: list[str] = []
    p = entry["plan"]
    lines.append(f"## {status_word(p['status'])} P{p['id']} {p['name']}".rstrip())
    if p.get("goal"):
        lines.append(f"> why: {p['goal']}")
    if p.get("description"):
        lines.append(f"> what: {p['description']}")
    _md_crit(lines, entry.get("criteria", []))
    _md_repos(lines, entry.get("repos", []))
    for link in entry.get("links", []):
        sha = str(link.get("sha", ""))[:12]
        subject = str(link.get("subject", "") or "").strip()
        lines.append(f"- commit: {sha} {subject}".rstrip())
    for sentry in entry.get("milestones", []):
        lines.extend(_md_milestone_lines(sentry))
    return "\n".join(lines)
