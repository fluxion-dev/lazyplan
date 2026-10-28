"""Read-only Source screen: browse where a plan row landed in each checkout."""

from __future__ import annotations

import webbrowser
from datetime import datetime
from typing import Any

try:
    from textual import on  # noqa: F401
    from textual.app import ComposeResult  # noqa: F401
    from textual.binding import Binding  # noqa: F401
    from textual.containers import Horizontal, Vertical, VerticalScroll  # noqa: F401
    from textual.screen import Screen  # noqa: F401
    from textual.widgets import Footer, Input, Static, Tree  # noqa: F401
    from textual.widgets.tree import TreeNode  # noqa: F401

    from ...tree_nav import NavTree  # noqa: F401

    _TEXTUAL_OK = True
except ImportError:  # pragma: no cover
    _TEXTUAL_OK = False

from ...design import SOURCE_MARKER_RICH, escape_markup
from ...source import (
    DiffFile,
    DiffLine,
    SourceCommit,
    SourceFile,
    SourcePull,
    SourceRepo,
    SourceTrail,
    build_source_trail,
    clear_diff_cache,
    parse_patch,
    read_diff,
)
from ...store import Store

DIFF_PREVIEW_LINES = 300
DIFF_PREVIEW_FILES = 20


def _when(timestamp: int) -> str:
    """Short local date for a commit timestamp."""
    if timestamp <= 0:
        return ""
    try:
        return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d")
    except (OverflowError, OSError, ValueError):
        return ""


def _commit_label(commit: SourceCommit) -> str:
    subject = escape_markup(commit.subject or "(no subject)")
    count = f" · {len(commit.files)} files" if commit.files else ""
    stale = " [red]stale[/]" if commit.stale else ""
    return f"[dim]{commit.short}[/] {subject}[dim]{count}[/]{stale} {SOURCE_MARKER_RICH}"


def _repo_label(repo: SourceRepo) -> str:
    state = "dirty" if repo.dirty else "clean"
    branch = repo.branch or ("detached" if repo.detached else "unknown")
    return (
        f"[bold]{escape_markup(repo.name)}[/] "
        f"[dim]{escape_markup(branch)} · {state} · {len(repo.commits)} commits"
        f" · {len(repo.pulls)} PRs[/] {SOURCE_MARKER_RICH}"
    )


def _pull_label(pull: SourcePull) -> str:
    title = escape_markup(pull.title or "")
    state = pull.state or "unknown"
    return f"[dim]PR #{pull.number}[/] {state} {title} {SOURCE_MARKER_RICH}".rstrip()


def _diff_gutter(line: DiffLine) -> str:
    """Aligned old/new line-number gutter for one diff line."""
    old = f"{line.old_no:>4}" if line.old_no is not None else "    "
    new = f"{line.new_no:>4}" if line.new_no is not None else "    "
    return f"[dim]{old} {new}[/]"


def _diff_row(line: DiffLine) -> str:
    """One diff line: colored add/remove, dim context, plain meta."""
    text = escape_markup(line.text)
    gutter = _diff_gutter(line)
    if line.kind == "add":
        return f"{gutter} [green]+{text}[/]"
    if line.kind == "remove":
        return f"{gutter} [red]-{text}[/]"
    if line.kind == "meta":
        return f"[dim]{text}[/]"
    return f"{gutter} {text}"


def _diff_rows(files: tuple[DiffFile, ...], max_files: int) -> list[str]:
    """Render file headers, hunk headers, and numbered lines up to a file cap."""
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
            rows.extend(_diff_row(line) for line in hunk.lines)
    return rows


if _TEXTUAL_OK:

    class SourceScreen(Screen):
        """Keyboard tree of repos, commits, files, and pull requests."""

        BINDINGS = [
            Binding("escape", "back", "Back", priority=True),
            Binding("o", "open", "Open"),
            Binding("y", "copy", "Copy"),
            Binding("slash", "filter", "Filter"),
            Binding("r", "refresh", "Refresh", show=False),
        ]

        def __init__(self, store: Store, kind: str, oid: int) -> None:
            super().__init__()
            self._store = store
            self._kind = kind
            self._oid = oid
            self._trail = SourceTrail(kind=kind, oid=oid, title="")
            self._filter = ""
            self._diff_cache: dict[tuple[str, str, str], list[str]] = {}

        def compose(self) -> ComposeResult:
            with Vertical(id="source-page"):
                yield Static("", id="source-head")
                yield Input(placeholder="filter source…", id="source-filter")
                with Horizontal(id="source-main"):
                    with VerticalScroll(id="source-tree-wrap"):
                        yield NavTree("source", id="source-tree")
                    with VerticalScroll(id="source-preview"):
                        yield Static("", id="source-preview-body")
                yield Footer(compact=True)

        def on_mount(self) -> None:
            self.query_one("#source-filter", Input).display = False
            self._load()
            self.query_one("#source-tree", NavTree).focus()

        def _load(self) -> None:
            """Start one background trail load; never block the UI thread."""
            head = f"{self._kind.capitalize()} #{self._oid}"
            self.query_one("#source-head", Static).update(f"{head}\n[dim]loading source…[/]")
            self.run_worker(self._load_worker, thread=True, exclusive=True)

        def _load_worker(self) -> None:
            trail = build_source_trail(self._store, self._kind, self._oid)
            try:
                self.app.call_from_thread(self._apply_trail, trail)
            except Exception:
                return

        def _apply_trail(self, trail: SourceTrail) -> None:
            self._trail = trail
            head = f"{self._kind.capitalize()} #{self._oid}"
            if self._trail.title:
                head += f" · {escape_markup(self._trail.title)}"
            summary = (
                f"[dim]{self._trail.commit_count} commits · "
                f"{self._trail.file_count} files · "
                f"{self._trail.pull_count} PRs"
                + (f" · {self._trail.stale_count} stale" if self._trail.stale_count else "")
                + "[/]"
            )
            self.query_one("#source-head", Static).update(f"{head}\n{summary}")
            self._build_tree()

        def _build_tree(self) -> None:
            tree = self.query_one("#source-tree", NavTree)
            tree.clear()
            tree.root.expand()
            if self._trail.empty:
                tree.root.add_leaf(
                    "No source linked. Run `lpui link`, `lpui task finish`, or `pr refresh`.",
                    data={"kind": "empty", "copy": ""},
                )
                self._preview(None)
                return
            needle = self._filter.strip().lower()
            for repo in self._trail.repos:
                if needle and not self._repo_matches(repo, needle):
                    continue
                repo_node = tree.root.add(_repo_label(repo), data=self._repo_data(repo))
                for commit in repo.commits:
                    if needle and not self._commit_matches(commit, needle):
                        continue
                    commit_node = repo_node.add(
                        _commit_label(commit), data=self._commit_data(repo, commit)
                    )
                    for item in commit.files:
                        if needle and needle not in item.path.lower():
                            continue
                        commit_node.add_leaf(
                            f"[dim]{escape_markup(item.path)}[/] {SOURCE_MARKER_RICH}",
                            data=self._file_data(repo, commit, item),
                        )
                for pull in repo.pulls:
                    if needle and needle not in f"pr {pull.number} {pull.title}".lower():
                        continue
                    repo_node.add_leaf(_pull_label(pull), data=self._pull_data(repo, pull))
                repo_node.expand()
            if not tree.root.children:
                tree.root.add_leaf(
                    f"No source matches {self._filter!r}.",
                    data={"kind": "empty", "copy": ""},
                )
            self._preview(tree.cursor_node)

        def _repo_matches(self, repo: SourceRepo, needle: str) -> bool:
            haystack = " ".join(
                [repo.name, repo.path, repo.remote, repo.branch, repo.slug]
                + [commit.subject for commit in repo.commits]
                + [item.path for commit in repo.commits for item in commit.files]
                + [pull.title for pull in repo.pulls]
            ).lower()
            return needle in haystack

        @staticmethod
        def _commit_matches(commit: SourceCommit, needle: str) -> bool:
            haystack = " ".join(
                [commit.sha, commit.subject, *[item.path for item in commit.files]]
            ).lower()
            return needle in haystack

        def _repo_data(self, repo: SourceRepo) -> dict[str, Any]:
            return {
                "kind": "repo",
                "repo": repo.path,
                "copy": repo.path,
                "url": "",
                "object": repo,
            }

        def _commit_data(self, repo: SourceRepo, commit: SourceCommit) -> dict[str, Any]:
            return {
                "kind": "commit",
                "repo": repo.path,
                "sha": commit.sha,
                "copy": commit.sha,
                "url": commit.url,
                "object": commit,
            }

        def _file_data(
            self, repo: SourceRepo, commit: SourceCommit, item: SourceFile
        ) -> dict[str, Any]:
            return {
                "kind": "file",
                "repo": repo.path,
                "sha": commit.sha,
                "path": item.path,
                "copy": item.path,
                "url": item.url,
                "object": item,
            }

        def _pull_data(self, repo: SourceRepo, pull: SourcePull) -> dict[str, Any]:
            return {
                "kind": "pull",
                "repo": repo.path,
                "number": pull.number,
                "copy": pull.url,
                "url": pull.url,
                "object": pull,
            }

        @on(Tree.NodeHighlighted, "#source-tree")
        def _on_highlight(self, event: Tree.NodeHighlighted) -> None:
            self._preview(event.node)

        def _preview(self, node: TreeNode | None) -> None:
            body = self.query_one("#source-preview-body", Static)
            data = node.data if node is not None else None
            text = "Select a repo, commit, file, or pull request."
            if isinstance(data, dict):
                kind = str(data.get("kind", ""))
                obj = data.get("object")
                repo = str(data.get("repo", "") or "")
                sha = str(data.get("sha", "") or "")
                if kind == "repo" and isinstance(obj, SourceRepo):
                    text = self._repo_preview(obj)
                elif kind == "commit" and isinstance(obj, SourceCommit):
                    text = self._commit_preview(obj, repo)
                elif kind == "file" and isinstance(obj, SourceFile):
                    text = self._file_preview(obj, repo, sha)
                elif kind == "pull" and isinstance(obj, SourcePull):
                    text = self._pull_preview(obj)
                else:
                    text = "No source linked for this row."
            body.update(text)
            try:
                self.query_one("#source-preview", VerticalScroll).scroll_home(animate=False)
            except Exception:
                pass

        def _repo_preview(self, repo: SourceRepo) -> str:
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
            lines.append(
                f"{len(repo.commits)} commits · {repo.file_count} files · {len(repo.pulls)} PRs"
            )
            return "\n".join(lines)

        def _commit_preview(self, commit: SourceCommit, repo: str = "") -> str:
            lines = [
                f"[bold]{commit.short}[/] {escape_markup(commit.subject or '(no subject)')}",
                f"[dim]{escape_markup(commit.sha)}[/]",
            ]
            meta = " · ".join(
                part
                for part in (
                    escape_markup(commit.author),
                    _when(commit.timestamp),
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
                lines.extend(["", *self._diff_block(repo, commit.sha)])
            return "\n".join(lines)

        def _file_preview(self, item: SourceFile, repo: str = "", sha: str = "") -> str:
            lines = [f"[bold]{escape_markup(item.path)}[/]"]
            if item.url:
                lines.append(item.url)
            else:
                lines.append("[dim]no web URL for this remote[/]")
            if repo and sha:
                lines.extend(["", *self._diff_block(repo, sha, item.path)])
            return "\n".join(lines)

        def _diff_block(self, repo: str, sha: str, path: str = "") -> list[str]:
            """Read and render a bounded diff preview, cached per row."""
            key = (repo, sha, path)
            cached = self._diff_cache.get(key)
            if cached is not None:
                return list(cached)
            rows = self._render_diff(repo, sha, path)
            self._diff_cache[key] = rows
            return list(rows)

        def _render_diff(self, repo: str, sha: str, path: str = "") -> list[str]:
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
            diff_rows = _diff_rows(files, DIFF_PREVIEW_FILES)
            budget = max(1, DIFF_PREVIEW_LINES - len(prefix))
            shown = prefix + diff_rows[:budget]
            remainder = len(diff_rows) - budget
            if remainder > 0:
                shown.append(f"[dim]+{remainder} more lines — o opens the full diff[/]")
            extra_files = len(files) - DIFF_PREVIEW_FILES
            if extra_files > 0:
                shown.append(f"[dim]+{extra_files} more files[/]")
            if read.truncated:
                shown.append("[dim]diff truncated — o opens the full commit[/]")
            return shown

        def _pull_preview(self, pull: SourcePull) -> str:
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

        def _selected(self) -> dict[str, Any] | None:
            node = self.query_one("#source-tree", NavTree).cursor_node
            data = node.data if node is not None else None
            return data if isinstance(data, dict) else None

        def action_back(self) -> None:
            """Close the source view."""
            self.app.pop_screen()

        def action_open(self) -> None:
            """Open the selected reference in the browser."""
            data = self._selected()
            url = str(data.get("url", "") or "") if data else ""
            if not url:
                self.notify("no web URL for this selection", timeout=3)
                return
            webbrowser.open(url)
            self.notify(f"opened {url}", timeout=4)

        def action_copy(self) -> None:
            """Copy the selected SHA, path, or URL."""
            data = self._selected()
            value = str(data.get("copy", "") or "") if data else ""
            if not value:
                self.notify("nothing to copy", timeout=3)
                return
            self.app.copy_to_clipboard(value)
            self.notify(f"copied {value}", timeout=3)

        def action_filter(self) -> None:
            """Focus the filter field."""
            field = self.query_one("#source-filter", Input)
            field.display = True
            field.focus()

        @on(Input.Changed, "#source-filter")
        def _on_filter_changed(self, event: Input.Changed) -> None:
            self._filter = event.value
            self._build_tree()

        @on(Input.Submitted, "#source-filter")
        def _on_filter_submitted(self, event: Input.Submitted) -> None:
            self._filter = event.value
            self.query_one("#source-filter", Input).display = False
            self._build_tree()
            self.query_one("#source-tree", NavTree).focus()

        def action_refresh(self) -> None:
            """Rebuild from cached data and drop in-memory diff bodies."""
            clear_diff_cache()
            self._diff_cache.clear()
            self._load()
            self.notify("source refreshed", timeout=3)
