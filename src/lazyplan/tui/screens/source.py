"""Read-only Source screen: browse where a plan row landed in each checkout."""

from __future__ import annotations

import webbrowser
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

from ...design import escape_markup
from ...source import (
    SourceCommit,
    SourceFile,
    SourcePull,
    SourceRepo,
    SourceTrail,
    build_source_trail,
    clear_diff_cache,
)
from ...store import Store
from ..views.source import (
    commit_label,
    commit_preview,
    file_preview,
    pull_label,
    pull_preview,
    render_diff,
    repo_label,
    repo_preview,
)

DIFF_PREVIEW_LINES = 300
DIFF_PREVIEW_FILES = 20


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
            width = self.app.size.width
            self.set_class(width < 80, "compact")
            self.set_class(width >= 120, "wide")
            page = self.query_one("#source-page")
            page.border_title = "SOURCE"
            self.query_one("#source-tree-wrap").border_title = "TRAIL"
            self.query_one("#source-preview").border_title = "DETAIL"
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
                repo_node = tree.root.add(repo_label(repo), data=self._repo_data(repo))
                for commit in repo.commits:
                    if needle and not self._commit_matches(commit, needle):
                        continue
                    commit_node = repo_node.add(
                        commit_label(commit), data=self._commit_data(repo, commit)
                    )
                    for item in commit.files:
                        if needle and needle not in item.path.lower():
                            continue
                        commit_node.add_leaf(
                            f"[dim]{escape_markup(item.path)}[/]",
                            data=self._file_data(repo, commit, item),
                        )
                for pull in repo.pulls:
                    if needle and needle not in f"pr {pull.number} {pull.title}".lower():
                        continue
                    repo_node.add_leaf(pull_label(pull), data=self._pull_data(repo, pull))
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
                    text = repo_preview(obj)
                elif kind == "commit" and isinstance(obj, SourceCommit):
                    text = commit_preview(obj, repo, self._diff_block(repo, sha))
                elif kind == "file" and isinstance(obj, SourceFile):
                    text = file_preview(obj, repo, sha, self._diff_block(repo, sha, str(obj.path)))
                elif kind == "pull" and isinstance(obj, SourcePull):
                    text = pull_preview(obj)
                else:
                    text = "No source linked for this row."
            body.update(text)
            try:
                self.query_one("#source-preview", VerticalScroll).scroll_home(animate=False)
            except Exception:
                pass

        def _diff_block(self, repo: str, sha: str, path: str = "") -> list[str]:
            """Read and render a bounded diff preview, cached per row."""
            key = (repo, sha, path)
            cached = self._diff_cache.get(key)
            if cached is not None:
                return list(cached)
            rows = render_diff(repo, sha, path, DIFF_PREVIEW_LINES, DIFF_PREVIEW_FILES)
            self._diff_cache[key] = rows
            return list(rows)

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
