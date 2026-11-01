"""Pure labels and preview bodies for the read-only source trail."""

from __future__ import annotations

from datetime import datetime

from ...design import escape_markup
from ...source import (
    DiffFile,
    DiffLine,
    SourceCommit,
    SourceFile,
    SourcePull,
    SourceRepo,
    parse_patch,
    read_diff,
)


def when(timestamp: int) -> str:
    """Short local date for a commit timestamp."""
    if timestamp <= 0:
        return ""
    try:
        return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d")
    except (OverflowError, OSError, ValueError):
        return ""


def commit_label(commit: SourceCommit) -> str:
    subject = escape_markup(commit.subject or "(no subject)")
    count = f" · {len(commit.files)} files" if commit.files else ""
    stale = " [red]stale[/]" if commit.stale else ""
    return f"[dim]{commit.short}[/] {subject}[dim]{count}[/]{stale}"


def repo_label(repo: SourceRepo) -> str:
    state = "dirty" if repo.dirty else "clean"
    branch = repo.branch or ("detached" if repo.detached else "unknown")
    return (
        f"[bold]{escape_markup(repo.name)}[/] "
        f"[dim]{escape_markup(branch)} · {state} · {len(repo.commits)} commits"
        f" · {len(repo.pulls)} PRs[/]"
    )


def pull_label(pull: SourcePull) -> str:
    title = escape_markup(pull.title or "")
    state = pull.state or "unknown"
    return f"[dim]PR #{pull.number}[/] {state} {title}".rstrip()


def diff_gutter(line: DiffLine) -> str:
    old = f"{line.old_no:>4}" if line.old_no is not None else "    "
    new = f"{line.new_no:>4}" if line.new_no is not None else "    "
    return f"[dim]{old} {new}[/]"


def diff_row(line: DiffLine) -> str:
    text = escape_markup(line.text)
    gutter = diff_gutter(line)
    if line.kind == "add":
        return f"{gutter} [green]+{text}[/]"
    if line.kind == "remove":
        return f"{gutter} [red]-{text}[/]"
    if line.kind == "meta":
        return f"[dim]{text}[/]"
    return f"{gutter} {text}"


def diff_rows(files: tuple[DiffFile, ...], max_files: int) -> list[str]:
    rows: list[str] = []
    for index, item in enumerate(files):
        if index >= max_files:
            break
        if item.binary:
            rows.append(f"[yellow]binary[/] {escape_markup(item.path)}")
            continue
        rows.append(f"[bold]{escape_markup(item.path)}[/]")
        for hunk in item.hunks:
            rows.append(f"[cyan]{escape_markup(hunk.header)}[/]")
            rows.extend(diff_row(line) for line in hunk.lines)
    return rows


def repo_preview(repo: SourceRepo) -> str:
    lines = [
        f"[bold]{escape_markup(repo.name)}[/]",
        f"[dim]{escape_markup(repo.path)}[/]",
    ]
    if repo.remote:
        lines.append(f"[dim]{escape_markup(repo.remote)}[/]")
    state = "dirty" if repo.dirty else "clean"
    track = f"{repo.ahead} ahead, {repo.behind} behind"
    lines.append(f"branch {escape_markup(repo.branch or 'unknown')} · {state} · {track}")
    if repo.error:
        lines.append(f"[red]{escape_markup(repo.error)}[/]")
    lines.append(f"{len(repo.commits)} commits · {repo.file_count} files · {len(repo.pulls)} PRs")
    return "\n".join(lines)


def commit_preview(commit: SourceCommit, repo: str, diff_lines: list[str]) -> str:
    lines = [
        f"[bold]{commit.short}[/] {escape_markup(commit.subject or '(no subject)')}",
        f"[dim]{escape_markup(commit.sha)}[/]",
    ]
    meta = " · ".join(
        part
        for part in (
            escape_markup(commit.author),
            when(commit.timestamp),
            ", ".join(commit.owners),
        )
        if part
    )
    if meta:
        lines.append(f"[dim]{meta}[/]")
    if commit.stale:
        lines.append("[red]stale: commit no longer resolves[/]")
    if commit.url:
        lines.append(commit.url)
    if commit.files:
        lines.extend(["", f"[dim]files {len(commit.files)}[/]"])
        for item in commit.files:
            lines.append(f"  {escape_markup(item.path)}")
    if repo:
        lines.extend(["", *diff_lines])
    return "\n".join(lines)


def file_preview(item: SourceFile, repo: str, sha: str, diff_lines: list[str]) -> str:
    lines = [f"[bold]{escape_markup(item.path)}[/]"]
    if item.url:
        lines.append(item.url)
    else:
        lines.append("[dim]no web URL for this remote[/]")
    if repo and sha:
        lines.extend(["", *diff_lines])
    return "\n".join(lines)


def pull_preview(pull: SourcePull) -> str:
    lines = [
        f"[bold]PR #{pull.number}[/] {escape_markup(pull.title or '')}",
        f"state {pull.state or 'unknown'}",
    ]
    if pull.checks and pull.checks != "none":
        lines.append(f"checks {pull.checks}")
    if pull.reviews and pull.reviews != "none":
        lines.append(f"reviews {pull.reviews}")
    if pull.merge_commit_sha:
        lines.append(f"merge {pull.merge_commit_sha[:12]}")
    if pull.owners:
        lines.append(f"[dim]{escape_markup(', '.join(pull.owners))}[/]")
    if pull.stale:
        lines.append("[red]stale: cached PR data[/]")
    if pull.url:
        lines.append(pull.url)
    return "\n".join(lines)


def render_diff(
    repo: str,
    sha: str,
    path: str,
    max_lines: int,
    max_files: int,
) -> list[str]:
    """Read and render a bounded diff preview."""
    read = read_diff(repo, sha, path)
    if read.state == "missing":
        return [f"[red]{escape_markup(read.detail or 'commit not available')}[/]"]
    if read.state == "merge":
        return [
            f"[yellow]{escape_markup(read.detail or 'merge commit')}[/]",
            "[dim]combined merge diffs are not rendered; press o to open it[/]",
        ]
    if read.state == "binary":
        return [f"[yellow]{escape_markup(read.detail or 'binary file')}[/]"]
    if read.state == "empty":
        return [f"[dim]{escape_markup(read.detail or 'no textual changes')}[/]"]
    if read.state == "error":
        return [f"[red]{escape_markup(read.detail or 'diff unavailable')}[/]"]
    files = parse_patch(read.patch)
    if not files:
        return ["[dim]no textual changes[/]"]
    prefix = ["[dim]root commit · full tree diff[/]"] if read.state == "root" else []
    rendered = diff_rows(files, max_files)
    budget = max(1, max_lines - len(prefix))
    shown = prefix + rendered[:budget]
    remainder = len(rendered) - budget
    if remainder > 0:
        shown.append(f"[dim]+{remainder} more lines — o opens the full diff[/]")
    extra_files = len(files) - max_files
    if extra_files > 0:
        shown.append(f"[dim]+{extra_files} more files[/]")
    if read.truncated:
        shown.append("[dim]diff truncated — o opens the full commit[/]")
    return shown
