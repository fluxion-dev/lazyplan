"""Pure labels and preview bodies for the read-only source trail."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from lazyplan.services.source import (
    CommitStats,
    FileStat,
    SourceCommit,
    SourceFile,
    SourcePull,
    SourceRepo,
    SourceTrail,
    read_diff_page,
)

from ...shared.design import escape_markup
from .diff_render import (
    DiffOptions,
    DiffPalette,
    diff_counts,
    render_unified,
)
from .diff_split import render_split


def summary_chips(trail: SourceTrail) -> str:
    """One chip row for the source head: commits, files, PRs, and stale rows."""
    chips = [
        f"[reverse] {trail.commit_count} commits [/]",
        f"[reverse] {trail.file_count} files [/]",
        f"[reverse] {trail.pull_count} PRs [/]",
    ]
    if trail.stale_count:
        chips.append(f"[bold red] {trail.stale_count} stale [/]")
    return " ".join(chips)


def when(timestamp: int) -> str:
    """Short local date for a commit timestamp."""
    if timestamp <= 0:
        return ""
    try:
        return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d")
    except (OverflowError, OSError, ValueError):
        return ""


_STATUS_GLYPH = {
    "add": ("A", "green"),
    "modify": ("M", "cyan"),
    "delete": ("D", "red"),
    "rename": ("R", "yellow"),
}


def commit_label(commit: SourceCommit, stats: CommitStats | None = None) -> str:
    subject = escape_markup(commit.subject or "(no subject)")
    files = len(stats.files) if stats is not None and stats.state == "ok" else len(commit.files)
    count = f" · {files} files" if files else ""
    changes = ""
    if stats is not None and stats.state == "ok":
        changes = f" [green]+{stats.additions}[/] [red]-{stats.deletions}[/]"
    stale = " [red]stale[/]" if commit.stale else ""
    return f"[dim]◆ {commit.short}[/] {subject}[dim]{count}[/]{changes}{stale}"


def file_label(item: SourceFile, stat: FileStat | None = None) -> str:
    """One file row: status glyph, path, and counts."""
    path = escape_markup(item.path)
    if stat is None:
        return f"[dim]▪ {path}[/]"
    letter, color = _STATUS_GLYPH.get(stat.status, ("M", "cyan"))
    name = path
    if stat.status == "rename" and stat.old_path:
        name = f"[dim]{escape_markup(stat.old_path)} →[/] {path}"
    if stat.binary:
        return f"[{color}]{letter}[/] {name} [yellow]binary[/]"
    counts = ""
    if stat.additions:
        counts += f" [green]+{stat.additions}[/]"
    if stat.deletions:
        counts += f" [red]-{stat.deletions}[/]"
    return f"[{color}]{letter}[/] {name}{counts}"


def repo_label(repo: SourceRepo) -> str:
    state = "dirty" if repo.dirty else "clean"
    icon = "●" if repo.dirty else "○"
    branch = repo.branch or ("detached" if repo.detached else "unknown")
    return (
        f"[bold]⎇ {escape_markup(repo.name)}[/] "
        f"[dim]{escape_markup(branch)} · {icon} {state} · {len(repo.commits)} commits[/]"
    )


def pull_label(pull: SourcePull) -> str:
    title = escape_markup(pull.title or "")
    state = pull.state or "unknown"
    return f"[dim]⇄ PR #{pull.number}[/] {state} {title}".rstrip()


def repo_matches(repo: SourceRepo, needle: str) -> bool:
    """True when a repo or any child row matches the filter."""
    haystack = " ".join(
        [repo.name, repo.path, repo.remote, repo.branch, repo.slug]
        + [commit.subject for commit in repo.commits]
        + [item.path for commit in repo.commits for item in commit.files]
        + [pull.title for pull in repo.pulls]
    ).lower()
    return needle in haystack


def commit_matches(commit: SourceCommit, needle: str) -> bool:
    """True when a commit SHA, subject, or path matches the filter."""
    haystack = " ".join([commit.sha, commit.subject, *[item.path for item in commit.files]]).lower()
    return needle in haystack


def repo_data(repo: SourceRepo) -> dict[str, Any]:
    """Tree payload for one repo row."""
    return {
        "kind": "repo",
        "repo": repo.path,
        "copy": repo.path,
        "url": "",
        "object": repo,
    }


def commit_data(repo: SourceRepo, commit: SourceCommit) -> dict[str, Any]:
    """Tree payload for one commit row."""
    return {
        "kind": "commit",
        "repo": repo.path,
        "sha": commit.sha,
        "copy": commit.sha,
        "url": commit.url,
        "owners": commit.owners,
        "object": commit,
    }


def file_data(
    repo: SourceRepo,
    commit: SourceCommit,
    item: SourceFile,
    stat: FileStat | None = None,
) -> dict[str, Any]:
    """Tree payload for one changed file, enriched when stats are known."""
    return {
        "kind": "file",
        "repo": repo.path,
        "sha": commit.sha,
        "path": item.path,
        "copy": item.path,
        "url": item.url,
        "owners": commit.owners,
        "object": item,
        "status": stat.status if stat is not None else "",
        "additions": stat.additions if stat is not None else 0,
        "deletions": stat.deletions if stat is not None else 0,
        "binary": stat.binary if stat is not None else False,
    }


def pull_data(repo: SourceRepo, pull: SourcePull) -> dict[str, Any]:
    """Tree payload for one pull request row."""
    return {
        "kind": "pull",
        "repo": repo.path,
        "number": pull.number,
        "copy": pull.url,
        "url": pull.url,
        "owners": pull.owners,
        "object": pull,
    }


def repo_preview(repo: SourceRepo) -> str:
    state = "dirty" if repo.dirty else "clean"
    icon = "●" if repo.dirty else "○"
    track = f"{repo.ahead} ahead, {repo.behind} behind"
    lines = [
        f"[bold]⎇ {escape_markup(repo.name)}[/] [dim]{escape_markup(repo.branch or 'unknown')}[/]",
        f"[dim]{escape_markup(repo.path)}[/]",
    ]
    if repo.remote:
        lines.append(f"[dim]{escape_markup(repo.remote)}[/]")
    lines.append(f"[dim]{icon} {state} · {track}[/]")
    if repo.error:
        lines.append(f"[red]{escape_markup(repo.error)}[/]")
    lines.append(
        f"[dim]⌁ {len(repo.commits)} commits · {repo.file_count} files · {len(repo.pulls)} PRs[/]"
    )
    return "\n".join(lines)


@dataclass(frozen=True)
class DiffPreview:
    """One page of rendered diff rows."""

    rows: tuple[str, ...] = ()
    offset: int = 0
    total: int = 0
    has_more: bool = False


def source_files(
    commit: SourceCommit,
    stats: CommitStats | None = None,
) -> tuple[tuple[SourceFile, FileStat | None], ...]:
    """Commit files in display order, enriched with stats when available."""
    by_path = (
        {item.path: item for item in stats.files}
        if stats is not None and stats.state == "ok"
        else {}
    )
    out: list[tuple[SourceFile, FileStat | None]] = []
    seen: set[str] = set()
    for item in commit.files:
        out.append((item, by_path.get(item.path)))
        seen.add(item.path)
    if stats is not None and stats.state == "ok":
        for stat in stats.files:
            if stat.path in seen:
                continue
            out.append((SourceFile(path=stat.path), stat))
    return tuple(out)


def commit_summary(commit: SourceCommit, stats: CommitStats | None = None) -> list[str]:
    """Two-line commit summary: subject, then metadata and totals."""
    lines = [
        f"[bold]◆ {commit.short}[/] {escape_markup(commit.subject or '(no subject)')}",
    ]
    parts = [escape_markup(commit.author), when(commit.timestamp)]
    if commit.owners:
        parts.append(", ".join(commit.owners))
    if stats is not None and stats.state == "ok":
        parts.append(f"{len(stats.files)} files")
        parts.append(f"+{stats.additions} -{stats.deletions}")
    meta = " · ".join(part for part in parts if part)
    if meta:
        lines.append(f"[dim]{meta}[/]")
    if commit.stale:
        lines.append("[red]stale: commit no longer resolves[/]")
    return lines


def commit_index(
    items: tuple[tuple[SourceFile, FileStat | None], ...],
    current: int,
) -> str:
    """One compact file index with the current path emphasized."""
    if not items:
        return "[dim]no changed files[/]"
    shown = items[:6]
    parts: list[str] = []
    for index, (item, _stat) in enumerate(shown):
        path = escape_markup(item.path)
        if index == current:
            parts.append(f"[bold cyan]▸ {path}[/]")
        else:
            parts.append(f"[dim]{path}[/]")
    if len(items) > len(shown):
        parts.append(f"[dim]+{len(items) - len(shown)} more[/]")
    head = f"[bold]files {current + 1}/{len(items)}[/]"
    return f"{head} " + " · ".join(parts)


def commit_preview(
    commit: SourceCommit,
    stats: CommitStats | None,
    items: tuple[tuple[SourceFile, FileStat | None], ...],
    current: int,
    diff_rows: tuple[str, ...] | list[str],
) -> str:
    """Commit summary, file index, and the current file's diff."""
    lines = commit_summary(commit, stats)
    lines.append(commit_index(items, current))
    if items:
        lines.extend(diff_rows)
    return "\n".join(lines)


def file_preview(
    commit: SourceCommit | None,
    items: tuple[tuple[SourceFile, FileStat | None], ...],
    current: int,
    diff_rows: tuple[str, ...] | list[str],
) -> str:
    """A file's diff with its commit and position for context."""
    if commit is None:
        head = f"[bold]file {current + 1}/{len(items)}[/]"
    else:
        head = (
            f"[dim]◆ {commit.short}[/] "
            f"{escape_markup(commit.subject or '(no subject)')} · "
            f"[bold]file {current + 1}/{len(items)}[/]"
        )
    if items:
        head += f" [dim]{escape_markup(items[current][0].path)}[/]"
    return "\n".join([head, *diff_rows])


def pull_preview(pull: SourcePull) -> str:
    lines = [
        f"[bold]⇄ PR #{pull.number}[/] {escape_markup(pull.title or '')}",
        f"[dim]state[/] {pull.state or 'unknown'}",
    ]
    if pull.checks and pull.checks != "none":
        lines.append(f"[dim]checks[/] {pull.checks}")
    if pull.reviews and pull.reviews != "none":
        lines.append(f"[dim]reviews[/] {pull.reviews}")
    if pull.merge_commit_sha:
        lines.append(f"[dim]merge[/] {pull.merge_commit_sha[:12]}")
    if pull.owners:
        lines.append(f"[dim]{escape_markup(', '.join(pull.owners))}[/]")
    if pull.stale:
        lines.append("[red]stale: cached PR data[/]")
    if pull.url:
        lines.append(pull.url)
    return "\n".join(lines)


def render_diff_preview(
    repo: str,
    sha: str,
    path: str,
    width: int,
    offset: int = 0,
    limit: int = 300,
    split: bool = False,
    wrap: bool = True,
    fold: bool = True,
) -> DiffPreview:
    """Render one page of a single file's diff without another git read."""
    page = read_diff_page(repo, sha, path, limit=1 if path else 20)
    read = page.read
    if read.state == "missing":
        message = f"[red]{escape_markup(read.detail or 'commit not available')}[/]"
        return DiffPreview(rows=(message,), total=1)
    if read.state == "merge":
        rows = (
            f"[yellow]{escape_markup(read.detail or 'merge commit')}[/]",
            "[dim]combined merge diffs are not rendered; press o to open it[/]",
        )
        return DiffPreview(rows=rows, total=len(rows))
    if read.state == "empty":
        message = f"[dim]{escape_markup(read.detail or 'no textual changes')}[/]"
        return DiffPreview(rows=(message,), total=1)
    if read.state == "error":
        message = f"[red]{escape_markup(read.detail or 'diff unavailable')}[/]"
        return DiffPreview(rows=(message,), total=1)
    if not page.files:
        return DiffPreview(rows=("[dim]no textual changes[/]",), total=1)
    palette = DiffPalette()
    options = DiffOptions(fold=fold, wrap=wrap)
    if split:
        result = render_split(page.files, width, palette=palette, options=options)
        if not result.available:
            return DiffPreview(rows=(f"[dim]{escape_markup(result.detail)}[/]",), total=1)
        rendered = list(result.rows)
    else:
        rendered = render_unified(page.files, width, palette=palette, options=options)
    prefix: list[str] = []
    if not path:
        added = sum(diff_counts(item)[0] for item in page.files)
        removed = sum(diff_counts(item)[1] for item in page.files)
        prefix.append(f"[dim]{page.total} files[/] · [green]+{added}[/] · [red]-{removed}[/]")
        if read.state == "root":
            prefix.append("[dim]root commit · full tree diff[/]")
    all_rows = prefix + rendered
    total = len(all_rows)
    start = max(0, min(offset, total))
    window = all_rows[start : start + max(1, limit)]
    has_more = start + len(window) < total
    if has_more:
        remaining = total - start - len(window)
        window.append(f"[dim]… {remaining} more lines · ctrl+d[/]")
    elif read.truncated:
        window.append("[dim]diff truncated — o opens the full commit[/]")
    return DiffPreview(rows=tuple(window), offset=start, total=total, has_more=has_more)
