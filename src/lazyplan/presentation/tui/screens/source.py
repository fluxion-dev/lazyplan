"""Read-only Source screen: browse where a plan row landed in each checkout."""

from __future__ import annotations

import webbrowser
from typing import Any

try:
    from textual import events, on  # noqa: F401
    from textual.app import ComposeResult  # noqa: F401
    from textual.binding import Binding  # noqa: F401
    from textual.containers import Horizontal, Vertical, VerticalScroll  # noqa: F401
    from textual.screen import Screen  # noqa: F401
    from textual.widgets import Input, Label, Static, Tree  # noqa: F401
    from textual.widgets.tree import TreeNode  # noqa: F401

    from ...shared.tree_nav import NavTree  # noqa: F401

    _TEXTUAL_OK = True
except ImportError:  # pragma: no cover
    _TEXTUAL_OK = False

from lazyplan.services.source import (
    CommitStats,
    SourceCommit,
    SourceFile,
    SourcePull,
    SourceRepo,
    SourceTrail,
    build_source_trail,
    clear_diff_cache,
    clear_stats_cache,
    read_commit_stats,
)

from ....core.ports.provenance import ProvenancePort
from ...shared.design import KIND_ICON, action_bar, escape_markup
from ..navigation import NAV_BINDINGS, NavigationMixin
from ..views.diff_split import MIN_SPLIT_WIDTH
from ..views.diff_style import DiffPalette
from ..views.source import (
    DiffPreview,
    commit_data,
    commit_label,
    commit_matches,
    commit_preview,
    file_data,
    file_label,
    file_preview,
    pull_data,
    pull_label,
    pull_preview,
    render_diff_preview,
    repo_data,
    repo_label,
    repo_matches,
    repo_preview,
    source_files,
    summary_chips,
)

DIFF_PREVIEW_LINES = 300


if _TEXTUAL_OK:

    class SourceScreen(NavigationMixin, Screen):
        """Keyboard tree of repos, commits, files, and pull requests."""

        navigation_name = "source"

        BINDINGS = [
            *NAV_BINDINGS,
            Binding("escape", "back", "Back", priority=True),
            Binding("enter", "open_owner", "Owner", priority=True),
            Binding("n", "next_file", "Next file"),
            Binding("p", "prev_file", "Prev file"),
            Binding("s", "toggle_split", "Split"),
            Binding("w", "toggle_wrap", "Wrap"),
            Binding("f", "toggle_fold", "Fold"),
            Binding("ctrl+d", "more", "More"),
            Binding("ctrl+u", "less", "Less"),
            Binding("o", "open", "Open"),
            Binding("y", "copy", "Copy"),
            Binding("slash", "filter", "Filter"),
            Binding("r", "refresh", "Refresh", show=False),
        ]

        def __init__(self, store: ProvenancePort, kind: str, oid: int) -> None:
            super().__init__()
            self._store = store
            self._kind = kind
            self._oid = oid
            self._trail = SourceTrail(kind=kind, oid=oid, title="")
            self._filter = ""
            self._diff_cache: dict[
                tuple[str, str, str, int, str, bool, bool, bool, int], DiffPreview
            ] = {}
            self._stats_loaded: set[tuple[str, str]] = set()
            self._stats: dict[tuple[str, str], CommitStats] = {}
            self._commit_nodes: dict[tuple[str, str], TreeNode] = {}
            self._file_index = 0
            self._view_key: tuple[str, str, str] | None = None
            self._page_offset = 0
            self._page_total = 0
            self._page_has_more = False
            self._current_node: TreeNode | None = None
            self._split_mode = False
            self._wrap_mode = True
            self._fold_mode = True

        def compose(self) -> ComposeResult:
            with Vertical(id="source-page"):
                yield Static("", id="source-head")
                yield Input(placeholder="filter source…", id="source-filter")
                with Horizontal(id="source-main"):
                    with VerticalScroll(id="source-tree-wrap"):
                        yield NavTree("source", id="source-tree", classes="plan-tree")
                    with VerticalScroll(id="source-preview"):
                        yield Static("", id="source-preview-body")
                yield Label("", id="source-hints")

        def on_mount(self) -> None:
            self._apply_width_classes(self.app.size.width)
            page = self.query_one("#source-page")
            page.border_title = " source "
            self.query_one("#source-tree-wrap").border_title = " trail "
            self.query_one("#source-preview").border_title = " diff "
            self.query_one("#source-filter", Input).display = False
            self._update_hints()
            self._load()
            self.query_one("#source-tree", NavTree).focus()

        def _apply_width_classes(self, width: int) -> None:
            """Switch between the stacked and side-by-side layouts."""
            self.set_class(width < 80, "compact")
            self.set_class(width < 100, "stacked")
            self.set_class(width >= 120, "wide")

        def on_resize(self, event: events.Resize) -> None:
            """Re-render the current preview after a width change."""
            self._apply_width_classes(event.size.width)
            if self._split_mode and event.size.width - 2 < MIN_SPLIT_WIDTH:
                self._split_mode = False
                self.notify(
                    f"side-by-side needs {MIN_SPLIT_WIDTH} columns; switched to unified",
                    timeout=3,
                )
            self._diff_cache.clear()
            node = self.query_one("#source-tree", NavTree).cursor_node
            if node is not None:
                self._preview(node)

        def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
            """Keep the filter field's keys free while it owns the keyboard."""
            if action in (
                "open_owner",
                "next_file",
                "prev_file",
                "more",
                "less",
                "toggle_split",
                "toggle_wrap",
                "toggle_fold",
            ):
                if self._focus_is_text():
                    return False
            return super().check_action(action, parameters)

        def _load(self) -> None:
            """Start one background trail load; never block the UI thread."""
            head = f"{KIND_ICON.get(self._kind, '')} {self._kind.capitalize()} #{self._oid}"
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
            head = (
                f"[bold]{KIND_ICON.get(self._kind, '')} {self._kind.capitalize()} #{self._oid}[/]"
            )
            if self._trail.title:
                head += f" [dim]·[/] {escape_markup(self._trail.title)}"
            summary = summary_chips(self._trail)
            self.query_one("#source-head", Static).update(f"{head}\n{summary}")
            self._build_tree()

        def _build_tree(self) -> None:
            tree = self.query_one("#source-tree", NavTree)
            tree.clear()
            tree.root.expand()
            self._commit_nodes.clear()
            if self._trail.empty:
                tree.root.add_leaf(
                    "No source linked. Run `lpui link`, `lpui task finish`, or `pr refresh`.",
                    data={"kind": "empty", "copy": ""},
                )
                self._preview(None)
                return
            needle = self._filter.strip().lower()
            for repo in self._trail.repos:
                if needle and not repo_matches(repo, needle):
                    continue
                repo_node = tree.root.add(repo_label(repo), data=repo_data(repo))
                for commit in repo.commits:
                    if needle and not commit_matches(commit, needle):
                        continue
                    key = (repo.path, commit.sha)
                    stats = self._stats.get(key)
                    by_path = (
                        {item.path: item for item in stats.files}
                        if stats is not None and stats.state == "ok"
                        else {}
                    )
                    commit_node = repo_node.add(
                        commit_label(commit, stats), data=commit_data(repo, commit)
                    )
                    self._commit_nodes[key] = commit_node
                    seen: set[str] = set()
                    for item in commit.files:
                        if needle and needle not in item.path.lower():
                            continue
                        stat = by_path.get(item.path)
                        seen.add(item.path)
                        commit_node.add_leaf(
                            file_label(item, stat),
                            data=file_data(repo, commit, item, stat),
                        )
                    for stat in by_path.values():
                        if stat.path in seen:
                            continue
                        item = SourceFile(path=stat.path)
                        commit_node.add_leaf(
                            file_label(item, stat),
                            data=file_data(repo, commit, item, stat),
                        )
                    if not commit.files and not by_path:
                        commit_node.add_leaf(
                            "[dim]…[/]",
                            data={"kind": "placeholder", "copy": ""},
                        )
                for pull in repo.pulls:
                    if needle and needle not in f"pr {pull.number} {pull.title}".lower():
                        continue
                    repo_node.add_leaf(pull_label(pull), data=pull_data(repo, pull))
                repo_node.expand()
            if not tree.root.children:
                tree.root.add_leaf(
                    f"No source matches {self._filter!r}.",
                    data={"kind": "empty", "copy": ""},
                )
            self._preview(tree.cursor_node)

        @on(Tree.NodeHighlighted, "#source-tree")
        def _on_highlight(self, event: Tree.NodeHighlighted) -> None:
            self._preview(event.node)

        @on(Tree.NodeExpanded, "#source-tree")
        def _on_expanded(self, event: Tree.NodeExpanded) -> None:
            """Load per-file status and counts the first time a commit opens."""
            data = event.node.data
            if not isinstance(data, dict) or data.get("kind") != "commit":
                return
            repo = str(data.get("repo", "") or "")
            sha = str(data.get("sha", "") or "")
            if not repo or not sha:
                return
            key = (repo, sha)
            if key in self._stats_loaded:
                return
            self._stats_loaded.add(key)
            self.run_worker(
                lambda: self._stats_worker(repo, sha),
                thread=True,
                exclusive=False,
            )

        def _stats_worker(self, repo: str, sha: str) -> None:
            stats = read_commit_stats(repo, sha)
            try:
                self.app.call_from_thread(self._apply_stats, repo, sha, stats)
            except Exception:
                return

        def _apply_stats(self, repo: str, sha: str, stats: CommitStats) -> None:
            """Paint cached stats onto an expanded commit and its file rows."""
            key = (repo, sha)
            self._stats[key] = stats
            node = self._commit_nodes.get(key)
            if node is None or stats.state != "ok":
                return
            data = node.data if isinstance(node.data, dict) else {}
            commit = data.get("object")
            if not isinstance(commit, SourceCommit):
                commit = SourceCommit(sha=sha)
            repo_obj = next((item for item in self._trail.repos if item.path == repo), None)
            if repo_obj is None:
                repo_obj = SourceRepo(path=repo, name="")
            node.set_label(commit_label(commit, stats))
            urls = {item.path: item.url for item in commit.files}
            by_path = {item.path: item for item in stats.files}
            seen: set[str] = set()
            for child in list(node.children):
                child_data = child.data if isinstance(child.data, dict) else {}
                kind = str(child_data.get("kind", ""))
                if kind == "placeholder":
                    child.remove()
                    continue
                if kind != "file":
                    continue
                path = str(child_data.get("path", "") or "")
                stat = by_path.get(path)
                if not stat:
                    continue
                item = SourceFile(path=path, url=urls.get(path, str(child_data.get("url") or "")))
                child.set_label(file_label(item, stat))
                child_data.update(file_data(repo_obj, commit, item, stat))
                seen.add(path)
            for stat in stats.files:
                if stat.path in seen:
                    continue
                item = SourceFile(path=stat.path, url=urls.get(stat.path, ""))
                node.add_leaf(
                    file_label(item, stat),
                    data=file_data(repo_obj, commit, item, stat),
                )
            current = self.query_one("#source-tree", NavTree).cursor_node
            if current is node:
                self._preview(node)

        def _preview(self, node: TreeNode | None, reset_page: bool = True) -> None:
            """Paint the selected repo, commit, file, or pull request."""
            body = self.query_one("#source-preview-body", Static)
            data = node.data if node is not None else None
            previous = self._view_key
            if reset_page or node is not self._current_node:
                self._page_offset = 0
            text = "Select a repo, commit, file, or pull request."
            key: tuple[str, str, str] | None = None
            preview = DiffPreview()
            if isinstance(data, dict):
                kind = str(data.get("kind", ""))
                obj = data.get("object")
                repo = str(data.get("repo", "") or "")
                sha = str(data.get("sha", "") or "")
                if kind == "repo" and isinstance(obj, SourceRepo):
                    key = (repo, "", "")
                    text = repo_preview(obj)
                elif kind == "commit" and isinstance(obj, SourceCommit):
                    if node is not self._current_node:
                        self._file_index = 0
                    stats = self._stats.get((repo, sha))
                    items = source_files(obj, stats)
                    if items:
                        self._file_index = min(max(0, self._file_index), len(items) - 1)
                        path = items[self._file_index][0].path
                        key = (repo, sha, path)
                        preview = self._diff_preview(repo, sha, path)
                        text = commit_preview(obj, stats, items, self._file_index, preview.rows)
                    else:
                        key = (repo, sha, "")
                        text = commit_preview(obj, stats, items, 0, ())
                elif kind == "file" and isinstance(obj, SourceFile):
                    commit = self._commit(repo, sha)
                    stats = self._stats.get((repo, sha))
                    items = source_files(commit, stats) if commit is not None else ((obj, None),)
                    current = next(
                        (
                            index
                            for index, (item, _stat) in enumerate(items)
                            if item.path == obj.path
                        ),
                        0,
                    )
                    self._file_index = current
                    key = (repo, sha, obj.path)
                    preview = self._diff_preview(repo, sha, obj.path)
                    text = file_preview(commit, items, current, preview.rows)
                elif kind == "pull" and isinstance(obj, SourcePull):
                    key = (repo, f"pr:{obj.number}", "")
                    text = pull_preview(obj)
                else:
                    text = "No source linked for this row."
            if key != previous:
                self._view_key = key
            self._page_total = preview.total
            self._page_has_more = preview.has_more
            self._current_node = node
            body.update(text)
            if reset_page:
                try:
                    self.query_one("#source-preview", VerticalScroll).scroll_home(animate=False)
                except Exception:
                    pass
            self._update_hints()

        def _repo(self, path: str) -> SourceRepo | None:
            return next((repo for repo in self._trail.repos if repo.path == path), None)

        def _palette(self) -> DiffPalette:
            """Build the diff palette from the active theme variables."""
            variables = {name: str(value) for name, value in self.app.theme_variables.items()}
            return DiffPalette.from_theme(variables)

        def _commit(self, repo: str, sha: str) -> SourceCommit | None:
            parent = self._repo(repo)
            if parent is None:
                return None
            return next((commit for commit in parent.commits if commit.sha == sha), None)

        def _diff_preview(self, repo: str, sha: str, path: str) -> DiffPreview:
            """One cached page of a single file's diff."""
            width = max(20, self.query_one("#source-preview").size.width - 2)
            key = (
                repo,
                sha,
                path,
                width,
                str(self.app.theme),
                self._split_mode,
                self._wrap_mode,
                self._fold_mode,
                self._page_offset,
            )
            cached = self._diff_cache.get(key)
            if cached is not None:
                return cached
            preview = render_diff_preview(
                repo,
                sha,
                path,
                width,
                offset=self._page_offset,
                limit=DIFF_PREVIEW_LINES,
                split=self._split_mode,
                wrap=self._wrap_mode,
                fold=self._fold_mode,
                palette=self._palette(),
            )
            self._diff_cache[key] = preview
            return preview

        def _update_hints(self) -> None:
            """Keep the footer in step with paging and file navigation."""
            items = [
                ("enter", "owner"),
                ("n/p", "file"),
                ("s", "unified" if self._split_mode else "split"),
                ("w", "nowrap" if self._wrap_mode else "wrap"),
                ("f", "unfold" if self._fold_mode else "fold"),
                ("y", "copy"),
                ("/", "find"),
            ]
            if self._page_has_more:
                items.append(("^d", "more"))
            if self._page_offset:
                items.append(("^u", "less"))
            items.append(("esc", "back"))
            bar = action_bar(("o", "open"), items)
            if self._page_total > DIFF_PREVIEW_LINES or self._page_offset:
                end = min(self._page_offset + DIFF_PREVIEW_LINES, self._page_total)
                bar += f" · [dim]{end}/{self._page_total}[/]"
            self.query_one("#source-hints", Label).update(bar)

        def _selected(self) -> dict[str, Any] | None:
            node = self.query_one("#source-tree", NavTree).cursor_node
            data = node.data if node is not None else None
            return data if isinstance(data, dict) else None

        def _file_nodes(self) -> tuple[TreeNode | None, TreeNode | None, list[TreeNode]]:
            """Current node, its commit node, and the commit's file rows."""
            node = self.query_one("#source-tree", NavTree).cursor_node
            data = node.data if node is not None else None
            if not isinstance(data, dict):
                return node, None, []
            kind = str(data.get("kind", ""))
            if kind == "file" and node is not None:
                commit_node = node.parent
            elif kind == "commit":
                commit_node = node
            else:
                return node, None, []
            if commit_node is None:
                return node, None, []
            files = [
                child
                for child in commit_node.children
                if isinstance(child.data, dict) and child.data.get("kind") == "file"
            ]
            return node, commit_node, files

        def _walk_file(self, step: int) -> None:
            node, commit_node, files = self._file_nodes()
            if not files or commit_node is None:
                self.notify("this row has no changed files", timeout=2)
                return
            data = node.data if node is not None else None
            current = -1
            if isinstance(data, dict) and data.get("kind") == "file" and node in files:
                current = files.index(node)
            target = files[(current + step) % len(files)]
            if not commit_node.is_expanded:
                commit_node.expand()
                self.call_after_refresh(self._move_file_cursor, target)
            else:
                self._move_file_cursor(target)

        def _move_file_cursor(self, node: TreeNode) -> None:
            """Select one file row and keep the tree focused."""
            tree = self.query_one("#source-tree", NavTree)
            tree.move_cursor(node)
            tree.focus()

        def action_next_file(self) -> None:
            """Move to the next file in the current commit."""
            self._walk_file(1)

        def action_prev_file(self) -> None:
            """Move to the previous file in the current commit."""
            self._walk_file(-1)

        def action_more(self) -> None:
            """Show the next page of the current diff."""
            if not self._page_has_more:
                self.notify("end of diff", timeout=2)
                return
            self._page_offset += DIFF_PREVIEW_LINES
            self._preview(self._current_node, reset_page=False)

        def action_less(self) -> None:
            """Show the previous page of the current diff."""
            if self._page_offset <= 0:
                self.notify("start of diff", timeout=2)
                return
            self._page_offset = max(0, self._page_offset - DIFF_PREVIEW_LINES)
            self._preview(self._current_node, reset_page=False)

        def _rerender_modes(self) -> None:
            """Drop cached pages and repaint the current row."""
            self._diff_cache.clear()
            self._preview(self._current_node, reset_page=False)

        def action_toggle_split(self) -> None:
            """Switch between unified and side-by-side diffs."""
            width = max(20, self.query_one("#source-preview").size.width - 2)
            if not self._split_mode and width < MIN_SPLIT_WIDTH:
                self.notify(
                    f"side-by-side needs {MIN_SPLIT_WIDTH} columns",
                    timeout=3,
                )
                return
            self._split_mode = not self._split_mode
            self._rerender_modes()

        def action_toggle_wrap(self) -> None:
            """Switch between wrapped and truncated long lines."""
            self._wrap_mode = not self._wrap_mode
            self._rerender_modes()

        def action_toggle_fold(self) -> None:
            """Fold or unfold long unchanged runs."""
            self._fold_mode = not self._fold_mode
            self._rerender_modes()

        def action_back(self) -> None:
            """Close the source view and restore the prior selection."""
            handler = getattr(self.app, "action_history_back", None)
            if callable(handler):
                handler()
            else:
                self.app.pop_screen()

        def action_open_owner(self) -> None:
            """Cross-link to the plan, milestone, or task that owns this row."""
            data = self._selected()
            if not data:
                return
            from ..views.provenance import owner_target

            target = owner_target(tuple(data.get("owners", ())))
            if target is None:
                self.notify("this row has no owning plan, milestone, or task", timeout=3)
                return
            opener = getattr(self.app, "select_row", None)
            if callable(opener):
                opener(target[0], target[1])
                return
            self.notify(f"{target[0]} #{target[1]}", timeout=3)

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
            clear_stats_cache()
            self._diff_cache.clear()
            self._stats_loaded.clear()
            self._stats.clear()
            self._commit_nodes.clear()
            self._load()
            self.notify("source refreshed", timeout=3)
