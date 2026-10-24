"""Modal-palette Textual TUI: nav tree + live preview, one status line.

Keys: j/k navigate, left/right fold, enter detail, c palette,
  escape clear. Press c then type a prefix (new, cycle, tick,
  fold, filter, ...) and enter runs the match.
  Mouse click selects; double-click opens detail.
Keyboard-only: agents use the `lpui` CLI against the same SQLite file; local edits
bump reactive rev, external DB changes arrive via fingerprint() poll + feed toast.
"""

from __future__ import annotations

import time
import webbrowser
from typing import Any, cast

try:
    from textual import events, on
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Horizontal, Vertical, VerticalScroll
    from textual.reactive import reactive
    from textual.widgets import Label, Static, Tree
    from textual.widgets.tree import TreeNode

    _TEXTUAL_OK = True
except ImportError:  # pragma: no cover
    _TEXTUAL_OK = False

from . import services
from .cli_parser import package_version
from .commands import COMMANDS, by_id, hint_bar
from .design import (
    APP_CSS,
    EMPTY_NO_PLANS,
    escape_markup,
    milestone_row,
    plan_row,
    repo_project_name,
    status_word,
    task_row,
    truncate,
)
from .messages import RowAction, SelectionChanged
from .models import Milestone, Plan, Status, Task
from .render import render_git_status
from .repo import repo_label
from .screens import (
    ConfirmScreen,
    DetailScreen,
    FilterPromptScreen,
    HelpScreen,
    NewMilestoneScreen,
    NewPlanScreen,
    NewTaskScreen,
    PaletteScreen,
)
from .source_screen import SourceScreen
from .store import Store
from .templates import load_template
from .upgrade import UpgradeError, detect, latest_version, notice_text
from .vcs import detect_backend

STATUS_CYCLE: list[Status | None] = [None, Status.TODO, Status.DOING, Status.DONE]
DOUBLE_CLICK_WINDOW = 0.5  # seconds between two clicks on one row

if _TEXTUAL_OK:

    class FoldTree(Tree):
        """Plan/milestone tree: j/k + arrows move, enter opens detail.

        Minimal keys own the tree; every mutation runs through the modal
        palette (c). Native Tree space/shift+space are parked
        here so they do nothing — status and folding live in the palette.
        """

        BINDINGS = [Binding("enter", "open_detail", "Detail")]

        def on_tree_node_highlighted(self, e: Tree.NodeHighlighted) -> None:
            """Bubble selection as a custom message (guide/events pattern)."""
            key = LazyplanApp._node_key(e.node)
            if key is not None:
                self.post_message(SelectionChanged(kind=key[0], oid=key[1]))

        def action_toggle_node(self) -> None:
            """Space: parked — use the modal palette for status changes."""
            return

        def action_toggle_expand_all(self) -> None:
            """Shift+space: parked — use the modal palette for folding."""
            return

        def action_open_detail(self) -> None:
            """Enter: post intent; App handles via @on."""
            app = cast("LazyplanApp", self.app)
            if app.selected is not None:
                kind, oid = app.selected
                self.post_message(RowAction("open-detail", kind, oid))
            else:
                app.action_open_detail()

        async def _on_click(self, event: events.Click) -> None:
            """Single click selects; two quick clicks on one row open detail."""
            await super()._on_click(event)
            app = cast("LazyplanApp", self.app)
            meta = event.style.meta
            if "line" not in meta or meta.get("toggle", False):
                return
            try:
                node = self.get_node_at_line(meta["line"])
            except IndexError:
                return
            if node is None:
                return
            key = LazyplanApp._node_key(node)
            if key is None:
                return
            # Messages-up: announce selection, then open on double-click.
            self.post_message(SelectionChanged(kind=key[0], oid=key[1]))
            if app.note_click(key):
                self.post_message(RowAction("open-detail", key[0], key[1]))

    class LazyplanApp(App):
        """Single-panel TUI: the plan tree."""

        TITLE = "lazyplan"
        CSS = APP_CSS
        ENABLE_COMMAND_PALETTE = False
        BINDINGS = [
            Binding("j", "cursor_down", "Down", show=False),
            Binding("k", "cursor_up", "Up", show=False),
            Binding("enter", "open_detail", "Open"),
            Binding("left", "fold_left", "Fold", show=False),
            Binding("right", "fold_right", "Unfold", show=False),
            Binding("escape", "clear_filter", "Back", show=False),
            Binding("c", "command_palette", "Palette"),
            Binding("n", "new_context", "New"),
            Binding("e", "edit_selection", "Edit"),
            Binding("s", "toggle_status", "Status"),
            Binding("x", "criteria", "Tick"),
            Binding("a", "add_criterion", "Criterion"),
            Binding("d", "delete", "Delete"),
            Binding("g", "source_trail", "Source"),
            Binding("z", "fold", "Fold", show=False),
            Binding("Z", "fold_all", "Fold all", show=False),
            Binding("slash", "filter_text", "Filter"),
            Binding("f", "filter_status", "Status filter", show=False),
            Binding("F", "filter_source", "Source filter", show=False),
            Binding("A", "toggle_show_all", "All plans", show=False),
            Binding("r", "refresh", "Refresh", show=False),
            Binding("question_mark", "help", "Help"),
            Binding("q", "quit", "Quit"),
        ]

        def __init__(self, store: Store) -> None:
            super().__init__()
            self.store = store
            self.selected: tuple[str, int] | None = None
            self.status_filter: Status | None = None
            self.show_all: bool = False
            self.filter_text: str = ""
            self.source_filter: str = "all"
            self._row_nodes: dict[tuple[str, int], TreeNode] = {}
            self._collapsed: set[tuple[str, int]] = set()
            self._expanded: set[tuple[str, int]] = set()
            self._last_click_key: tuple[str, int] | None = None
            self._last_click_at: float = 0.0
            self._fp: Any = store.fingerprint()
            self._update_notice: str | None = None
            self._update_toasted: bool = False
            self._pending_note: str = ""
            self._mounted: bool = False
            self._refreshing: bool = False
            self._git_cache: dict[str, tuple[float, dict[str, Any]]] = {}

        # Reactive revision: local mutations bump rev; watch_rev refreshes.
        # External CLI writes still arrive via _poll fingerprint check.
        rev = reactive(0, init=False)

        def watch_rev(self, _old: int, _new: int) -> None:
            if not self._mounted:
                return
            try:
                self._fp = self.store.fingerprint()
            except Exception:
                pass
            note = self._pending_note
            self._pending_note = ""
            try:
                self.refresh_all(note)
            except Exception:
                pass

        def compose(self) -> ComposeResult:
            with Vertical(id="panel"):
                with Horizontal(id="main"):
                    with Vertical(id="nav"):
                        yield FoldTree("plans", id="tree")
                    with VerticalScroll(id="preview"):
                        yield Static("", id="preview-body")
            yield Label("", id="hints")
            yield Label("", id="status")

        def on_mount(self) -> None:
            self._mounted = True
            self._apply_layout()
            self.refresh_all("ready — ? for help")
            self.call_after_refresh(lambda: self.refresh_all())
            self.set_interval(1.0, self._poll)
            self.run_worker(self._check_update, thread=True, exclusive=True)
            self.query_one("#tree", Tree).focus()

        async def _on_resize(self, event: events.Resize) -> None:
            """Textual stops Resize at the App; re-apply the shell after it."""
            await super()._on_resize(event)
            self._apply_layout(event.size.width)
            if self._mounted:
                self.call_after_refresh(self.refresh_all)

        def _apply_layout(self, width: int | None = None) -> None:
            """Two panes when there is room; one pane on narrow terminals."""
            try:
                main = self.query_one("#main", Horizontal)
            except Exception:
                return
            available = self.size.width if width is None else width
            main.set_class(available < 100, "narrow")

        def _check_update(self) -> None:
            """One background latest-version check per session; silent on failure."""
            try:
                latest = latest_version()
            except UpgradeError:
                return
            notice = notice_text(detect(), package_version(), latest)
            if notice is not None:
                self.call_from_thread(self._announce_update, notice)

        def _announce_update(self, notice: str) -> None:
            self._update_notice = notice
            if not self._update_toasted:
                self._update_toasted = True
                self.notify(notice, timeout=8)
            self.refresh_all()

        # -- selection --------------------------------------------------
        def _track(self, node: TreeNode) -> None:
            data = getattr(node, "data", None)
            if isinstance(data, dict) and "kind" in data and "id" in data:
                self.selected = (data["kind"], int(data["id"]))
                self.update_preview()

        def on_tree_node_highlighted(self, e: Tree.NodeHighlighted) -> None:
            self._track(e.node)

        @on(SelectionChanged)
        def _on_selection_changed(self, e: SelectionChanged) -> None:
            """Custom message (bubbles FoldTree -> App): track cursor."""
            self.selected = (e.kind, e.oid)
            self.update_preview()

        def _preview_tasks(self, kind: str, full: dict[str, Any]) -> list[dict[str, Any]]:
            """Flat task dicts for a preview card (plan/milestone/task)."""
            if kind == "plan":
                return [
                    task for entry in full.get("milestones", []) for task in entry.get("tasks", [])
                ]
            if kind == "milestone":
                return [entry.get("task", {}) for entry in full.get("tasks", [])]
            return [full.get("task", {})]

        def _preview_title(self, kind: str, oid: int, obj: dict[str, Any]) -> list[str]:
            title = str(obj.get("title", obj.get("name", "")))
            status = str(obj.get("status", ""))
            label = {"plan": "P", "milestone": "M", "task": "T"}[kind]
            lines = [
                f"{status_word(status, 'rich')} "
                f"[dim]{label}{oid}[/] [bold]{escape_markup(title)}[/]"
            ]
            if kind == "milestone":
                lines.append(f"[dim]P{obj.get('plan_id')} › M{oid}[/]")
            elif kind == "task":
                milestone = self.store.get_milestone(int(obj.get("milestone_id", 0)))
                plan_id = milestone.plan_id if milestone else "?"
                lines.append(f"[dim]P{plan_id} › M{obj.get('milestone_id')} › T{oid}[/]")
            return lines

        def _git_state(self, path: str) -> dict[str, Any]:
            """Cached branch/dirty state for a checkout (5s TTL)."""
            now = time.time()
            cached = self._git_cache.get(path)
            if cached is not None and now - cached[0] < 5.0:
                return cached[1]
            state: dict[str, Any] = {
                "branch": "",
                "dirty": False,
                "ahead": 0,
                "behind": 0,
                "upstream": "",
                "detached": False,
            }
            backend, root = detect_backend(path)
            if backend is not None and root is not None:
                status = backend.status(root)
                state.update(
                    {
                        "branch": status.branch,
                        "dirty": status.dirty,
                        "ahead": status.ahead,
                        "behind": status.behind,
                        "upstream": status.upstream,
                        "detached": status.detached,
                    }
                )
            self._git_cache[path] = (now, state)
            return state

        def _git_preview_bits(self, repos: list[dict[str, Any]]) -> list[str]:
            """Compact branch/dirty bits for the preview's linked checkouts."""
            bits: list[str] = []
            for repo in repos[:2]:
                path = str(repo.get("repo_path", "") or "")
                if not path:
                    continue
                state = self._git_state(path)
                branch = state["branch"]
                if not branch:
                    branch = "detached" if state["detached"] else "unknown"
                name = repo_project_name(repo) or path
                dirty = " dirty" if state["dirty"] else " clean"
                bits.append(f"{name} {branch}{dirty}")
            return bits

        def _preview_acceptance(self, lines: list[str], crits: list[dict]) -> None:
            if not crits:
                return
            crit_done = sum(1 for crit in crits if crit.get("done"))
            open_crits = [crit for crit in crits if not crit.get("done")]
            tail = f" · {len(open_crits)} open" if open_crits else " · complete"
            lines.extend(["", f"[dim]acceptance {crit_done}/{len(crits)}{tail}[/]"])
            for crit in open_crits[:3]:
                lines.append(f"  · {escape_markup(str(crit.get('text', '')))}")

        def _preview_source_summary(
            self,
            lines: list[str],
            links: list[dict],
            forge: list[dict],
            repos: list[dict],
        ) -> None:
            if links or forge or repos:
                bits = []
                if links:
                    bits.append(f"{len(links)} commits")
                if forge:
                    bits.append(f"{len(forge)} PRs")
                if repos:
                    names = [name for name in (repo_project_name(r) for r in repos) if name]
                    bits.append(
                        "repos: " + ", ".join(names[:3]) if names else f"{len(repos)} repos"
                    )
                lines.append(f"[dim]{' · '.join(bits)}[/]")
            if not links:
                return
            newest = max(links, key=lambda link: int(link.get("timestamp", 0) or 0))
            files = len({path for link in links for path in link.get("files", [])})
            stale = sum(1 for link in links if link.get("stale"))
            last = (
                f"last {str(newest.get('sha', ''))[:12]} "
                f"{escape_markup(str(newest.get('subject', '') or '(no subject)'))}"
            )
            if files:
                last += f" · {files} files"
            if stale:
                last += f" · {stale} stale"
            lines.append(f"[dim]{last}[/]")

        def _preview_common(self, lines: list[str], full: dict[str, Any]) -> None:
            self._preview_acceptance(lines, full.get("criteria", []))
            links = full.get("effective_links") or full.get("links", [])
            forge = full.get("effective_forge_links") or full.get("forge_links", [])
            repos = full.get("effective_repos") or full.get("repos") or []
            self._preview_source_summary(lines, links, forge, repos)
            git_bits = self._git_preview_bits(repos)
            if git_bits:
                lines.append(f"[dim]git: {' · '.join(git_bits)}[/]")

        def _preview_plan(self, full: dict[str, Any], oid: int) -> list[str]:
            obj = full.get("plan", {})
            lines = self._preview_title("plan", oid, obj)
            tasks = self._preview_tasks("plan", full)
            milestones = full.get("milestones", [])
            if tasks:
                done = sum(1 for task in tasks if task.get("status") == "done")
                lines.append(f"[dim]{done}/{len(tasks)} tasks · {len(milestones)} milestones[/]")
            goal = str(obj.get("goal", "") or "").strip()
            desc = str(obj.get("description", "") or "").strip()
            if goal:
                lines.extend(["", "[dim]why[/]", goal])
            if desc:
                lines.extend(["", "[dim]what[/]", desc])
            open_tasks = [task for task in tasks if task.get("status") != "done"]
            if open_tasks:
                lines.extend(["", "[dim]next[/]"])
                for task in open_tasks[:3]:
                    lines.append(
                        f"  {status_word(str(task.get('status', '')), 'rich')} "
                        f"[dim]T{task.get('id')}[/] {escape_markup(str(task.get('title', '')))}"
                    )
            self._preview_common(lines, full)
            return lines

        def _preview_milestone(self, full: dict[str, Any], oid: int) -> list[str]:
            obj = full.get("milestone", {})
            lines = self._preview_title("milestone", oid, obj)
            tasks = self._preview_tasks("milestone", full)
            if tasks:
                done = sum(1 for task in tasks if task.get("status") == "done")
                lines.append(f"[dim]{done}/{len(tasks)} tasks[/]")
            desc = str(obj.get("description", "") or "").strip()
            if desc:
                lines.extend(["", "[dim]details[/]", desc])
            open_tasks = [task for task in tasks if task.get("status") != "done"]
            if open_tasks:
                lines.extend(["", "[dim]next[/]"])
                for task in open_tasks[:3]:
                    lines.append(
                        f"  {status_word(str(task.get('status', '')), 'rich')} "
                        f"[dim]T{task.get('id')}[/] {escape_markup(str(task.get('title', '')))}"
                    )
            self._preview_common(lines, full)
            return lines

        def _preview_task(self, full: dict[str, Any], oid: int) -> list[str]:
            obj = full.get("task", {})
            lines = self._preview_title("task", oid, obj)
            desc = str(obj.get("description", "") or "").strip()
            if desc:
                lines.extend(["", "[dim]details[/]", desc])
            self._preview_common(lines, full)
            return lines

        def update_preview(self) -> None:
            """Selection preview: a bounded summary, never the full plan."""
            try:
                body = self.query_one("#preview-body", Static)
            except Exception:
                return
            try:
                total_plans = self.store.counts()["plans"]
            except Exception:
                total_plans = 1
            if total_plans == 0:
                body.update(EMPTY_NO_PLANS)
                return
            if self.selected is None:
                body.update("select a plan (j/k or click) — enter opens it")
                return
            kind, oid = self.selected
            try:
                full = self.store.get_full(kind, oid)
            except Exception:
                body.update(f"{kind} {oid} — gone, press r")
                return
            if full is None:
                body.update(f"{kind} {oid} — gone, press r")
                return
            if kind == "plan":
                lines = self._preview_plan(full, oid)
            elif kind == "milestone":
                lines = self._preview_milestone(full, oid)
            else:
                lines = self._preview_task(full, oid)
            lines.extend(["", "[dim]enter open · e edit[/]"])
            body.update("\n".join(lines))

        @on(RowAction)
        def _on_row_action(self, e: RowAction) -> None:
            """Custom intents bubble here; App owns the side effects."""
            if e.action == "toggle-status":
                self.action_toggle_status()
            elif e.action == "open-detail":
                if e.kind is not None and e.oid is not None:
                    self._open_detail(e.kind, e.oid)
                else:
                    self.action_open_detail()
            elif e.action == "fold-all":
                self.action_fold_all()
            elif e.action == "detail-saved":
                self._saved("saved detail")
            e.stop()

        @staticmethod
        def _node_key(node: TreeNode) -> tuple[str, int] | None:
            data = getattr(node, "data", None)
            if isinstance(data, dict) and "kind" in data and "id" in data:
                return (str(data["kind"]), int(data["id"]))
            return None

        def on_tree_node_collapsed(self, e: Tree.NodeCollapsed) -> None:
            """Remember mouse folds across refreshes/polls."""
            if self._refreshing:
                return
            key = self._node_key(e.node)
            if key is not None and key[0] in ("plan", "milestone"):
                self._collapsed.add(key)
                self._expanded.discard(key)

        def on_tree_node_expanded(self, e: Tree.NodeExpanded) -> None:
            if self._refreshing:
                return
            key = self._node_key(e.node)
            if key is not None:
                self._collapsed.discard(key)
                if key[0] in ("plan", "milestone"):
                    self._expanded.add(key)

        def action_cursor_down(self) -> None:
            self.query_one("#tree", Tree).action_cursor_down()

        def action_cursor_up(self) -> None:
            self.query_one("#tree", Tree).action_cursor_up()

        def action_fold(self) -> None:
            """Toggle the selected plan/milestone open/closed (z)."""
            if self.selected is None:
                self.notify("select a row first (z folds it)")
                return
            node = self._row_nodes.get(self.selected)
            if node is None or not node.allow_expand or not node.children:
                self.notify("nothing to fold here")
                return
            key = self.selected
            if key in self._expanded:
                node.collapse()
                self._expanded.discard(key)
                self._collapsed.add(key)
                self.refresh_all(f"{key[0]} {key[1]} folded")
            else:
                node.expand()
                self._expanded.add(key)
                self._collapsed.discard(key)
                self.refresh_all(f"{key[0]} {key[1]} unfolded")

        def action_fold_all(self) -> None:
            """Collapse every plan/milestone, or re-open all when fully expanded (Z)."""
            keys = [k for k, n in self._row_nodes.items() if n.allow_expand and n.children]
            if not keys:
                self.notify("nothing to fold")
                return
            if all(k in self._expanded for k in keys):
                for k in keys:
                    self._row_nodes[k].collapse()
                self._expanded.clear()
                self._collapsed.update(keys)
                self.refresh_all(f"folded {len(keys)} rows")
            else:
                for k in keys:
                    self._row_nodes[k].expand()
                self._expanded.update(keys)
                self._collapsed.difference_update(keys)
                self.refresh_all("unfolded all")

        def _children_of(self, kind: str, oid: int) -> list[tuple[str, int]]:
            """Visible child row keys, in tree order."""
            if kind == "plan":
                return [
                    ("milestone", s.id)
                    for s in self.store.list_milestones(oid)
                    if ("milestone", s.id) in self._row_nodes
                ]
            if kind == "milestone":
                return [
                    ("task", t.id)
                    for t in self.store.list_tasks(oid)
                    if ("task", t.id) in self._row_nodes
                ]
            return []

        def _parent_of(self, kind: str, oid: int) -> tuple[str, int] | None:
            if kind == "milestone":
                s = self.store.get_milestone(oid)
                return ("plan", s.plan_id) if s else None
            if kind == "task":
                t = self.store.get_task(oid)
                return ("milestone", t.milestone_id) if t else None
            return None

        def action_fold_left(self) -> None:
            """Left: collapse the header, else jump to its parent."""
            if self.selected is None:
                return
            kind, oid = self.selected
            node = self._row_nodes.get(self.selected)
            if (
                node is not None
                and node.allow_expand
                and node.children
                and (kind, oid) in self._expanded
            ):
                node.collapse()
                self._expanded.discard((kind, oid))
                self._collapsed.add((kind, oid))
                self.refresh_all(f"{kind} {oid} folded")
                return
            parent = self._parent_of(kind, oid)
            if parent is not None and parent in self._row_nodes:
                self.query_one("#tree", Tree).move_cursor(self._row_nodes[parent])

        def action_fold_right(self) -> None:
            """Right: expand the header, else jump to its first child."""
            if self.selected is None:
                return
            kind, oid = self.selected
            node = self._row_nodes.get(self.selected)
            if (
                node is not None
                and node.allow_expand
                and node.children
                and (kind, oid) not in self._expanded
            ):
                node.expand()
                self._expanded.add((kind, oid))
                self._collapsed.discard((kind, oid))
                self.refresh_all(f"{kind} {oid} unfolded")
                return
            for child in self._children_of(kind, oid):
                self.query_one("#tree", Tree).move_cursor(self._row_nodes[child])
                return

        # -- polling (fingerprint, not just mtime) ----------------------
        def _poll(self) -> None:
            """External-change detector; local edits go through rev."""
            try:
                fp = self.store.fingerprint()
            except Exception:
                return
            if fp != self._fp:
                events_ = self.store.feed(1)
                note = "db changed — refreshed"
                if events_:
                    e = events_[0]
                    note = f"[{e['actor']}] {e['kind']}/{e['action']}: {e['detail']}"
                    try:
                        self.notify(note, timeout=4)
                    except Exception:
                        pass
                self._pending_note = note
                self.rev += 1

        # -- rendering ---------------------------------------------------
        def _source_stats(self) -> dict[tuple[str, int], tuple[int, int, int]]:
            """Direct plus descendant provenance counts per row, one store read each."""
            vcs = self.store.vcs_links_map()
            forge = self.store.forge_links_map()

            def direct(kind: str, oid: int) -> tuple[int, int, int]:
                links = vcs.get((kind, oid), [])
                pulls = forge.get((kind, oid), [])
                return (
                    len(links),
                    len(pulls),
                    sum(1 for link in links if link.stale) + sum(1 for link in pulls if link.stale),
                )

            stats: dict[tuple[str, int], tuple[int, int, int]] = {}
            for plan, milestones in services.tree(self.store, status=self.status_filter):
                pc, pp, ps = direct("plan", plan.id)
                for milestone, tasks in milestones:
                    mc, mp, ms = direct("milestone", milestone.id)
                    for task in tasks:
                        tc, tp, ts = direct("task", task.id)
                        stats[("task", task.id)] = (tc, tp, ts)
                        mc, mp, ms = mc + tc, mp + tp, ms + ts
                    stats[("milestone", milestone.id)] = (mc, mp, ms)
                    pc, pp, ps = pc + mc, pp + mp, ps + ms
                stats[("plan", plan.id)] = (pc, pp, ps)
            return stats

        def _source_match(self, stats: tuple[int, int, int]) -> bool:
            commits, pulls, stale = stats
            if self.source_filter == "linked":
                return commits > 0 or pulls > 0
            if self.source_filter == "pr":
                return pulls > 0
            if self.source_filter == "stale":
                return stale > 0
            if self.source_filter == "unlinked":
                return commits == 0 and pulls == 0
            return True

        def _filter_source_tree(
            self,
            base: list[tuple[Plan, list[tuple[Milestone, list[Task]]]]],
            stats: dict[tuple[str, int], tuple[int, int, int]],
        ) -> list[tuple[Plan, list[tuple[Milestone, list[Task]]]]]:
            """Keep rows whose cached provenance matches the active source filter."""
            if self.source_filter == "all":
                return base
            out: list[tuple[Plan, list[tuple[Milestone, list[Task]]]]] = []
            for plan, milestones in base:
                kept_ms: list[tuple[Milestone, list[Task]]] = []
                for milestone, tasks in milestones:
                    kept_tasks = [
                        task
                        for task in tasks
                        if self._source_match(stats.get(("task", task.id), (0, 0, 0)))
                    ]
                    if kept_tasks or self._source_match(
                        stats.get(("milestone", milestone.id), (0, 0, 0))
                    ):
                        kept_ms.append((milestone, kept_tasks))
                if kept_ms or self._source_match(stats.get(("plan", plan.id), (0, 0, 0))):
                    out.append((plan, kept_ms))
            return out

        def _filtered_tree(
            self,
        ) -> list[tuple[Plan, list[tuple[Milestone, list[Task]]]]]:
            if self.show_all or self.filter_text.strip():
                base = services.tree(self.store, status=self.status_filter)
            else:
                base = services.tree(
                    self.store, status=self.status_filter, limit=services.DEFAULT_PLAN_LIMIT
                )
            if self.source_filter != "all":
                base = self._filter_source_tree(base, self._source_stats())
            query = self.filter_text.strip().lower()
            if not query:
                return base
            filtered: list[tuple[Plan, list[tuple[Milestone, list[Task]]]]] = []
            for p, milestones in base:
                if query in p.name.lower():
                    filtered.append((p, milestones))
                    continue
                kept_ms: list[tuple[Milestone, list[Task]]] = []
                for s, tasks in milestones:
                    if query in s.title.lower():
                        kept_ms.append((s, list(tasks)))
                        continue
                    hits = [t for t in tasks if query in t.title.lower()]
                    if hits:
                        kept_ms.append((s, hits))
                if kept_ms:
                    filtered.append((p, kept_ms))
            return filtered

        def action_clear_filter(self) -> None:
            if len(self.screen_stack) > 1:
                return
            if self.filter_text:
                self.filter_text = ""
                self._pending_note = "filter cleared"
                try:
                    self.rev += 1
                except Exception:
                    self.refresh_all("filter cleared")
                try:
                    self.query_one("#tree", Tree).focus()
                except Exception:
                    pass

        def _progress_map(self) -> dict[tuple[str, int], tuple[int, int]]:
            """Task progress per plan and milestone, independent of filters."""
            out: dict[tuple[str, int], tuple[int, int]] = {}
            for plan, milestones in services.tree(self.store, status=None, archived="show"):
                all_tasks = [task for _, tasks in milestones for task in tasks]
                out[("plan", plan.id)] = (
                    sum(1 for task in all_tasks if task.status == Status.DONE),
                    len(all_tasks),
                )
                for milestone, tasks in milestones:
                    out[("milestone", milestone.id)] = (
                        sum(1 for task in tasks if task.status == Status.DONE),
                        len(tasks),
                    )
            return out

        def _status_text(self, counts: dict[str, int], note: str) -> str:
            """Human counts, filter state, update notice, and the latest event."""
            open_tasks = counts["tasks"] - counts["tasks_done"]
            bits = [
                repo_label(self.store.path),
                f"{counts['plans']} plans",
                f"{open_tasks} open",
                f"{counts['plans_doing']} doing",
            ]
            if self.status_filter is not None:
                bits.append(f"status {self.status_filter.value}")
            if self.source_filter != "all":
                bits.append(f"source {self.source_filter}")
            if self.filter_text.strip():
                bits.append(f'filter "{self.filter_text.strip()}"')
            if not self.show_all:
                bits.append(f"recent {services.DEFAULT_PLAN_LIMIT}")
            if self._update_notice is not None:
                bits.append("update available")
            text = " · ".join(bits)
            if note:
                text += f" — {note}"
            events = self.store.feed(1)
            if events:
                event = events[0]
                text += f" · last: {event['actor']} {event['kind']}/{event['action']}: {event['detail']}"
            return truncate(text, max(10, self.size.width - 2))

        def _row_width(self, tree: Tree, depth: int) -> int:
            """Usable label width for a row at `depth`, excluding tree guides."""
            base = tree.size.width or (
                max(20, self.size.width // 2)
                if self.size.width >= 100
                else max(20, self.size.width)
            )
            return max(10, base - 5 - depth)

        def _build_rows(
            self,
            root: Any,
            tree: Tree,
            filtered: list,
            progress: dict,
            forge_map: dict,
            vcs_map: dict,
            source_stats: dict,
        ) -> None:
            """Create plan/milestone/task nodes for one refresh."""
            for plan, milestones in filtered:
                plan_node = root.add(
                    plan_row(
                        plan,
                        progress=progress.get(("plan", plan.id)),
                        width=self._row_width(tree, 3),
                        source_counts=source_stats.get(("plan", plan.id)),
                    ),
                    data={"kind": "plan", "id": plan.id},
                    allow_expand=bool(milestones),
                )
                self._row_nodes[("plan", plan.id)] = plan_node
                for milestone, tasks in milestones:
                    milestone_node = plan_node.add(
                        milestone_row(
                            milestone,
                            self.store,
                            progress=progress.get(("milestone", milestone.id)),
                            width=self._row_width(tree, 7),
                            source_counts=source_stats.get(("milestone", milestone.id)),
                        ),
                        data={"kind": "milestone", "id": milestone.id},
                        allow_expand=bool(tasks),
                    )
                    self._row_nodes[("milestone", milestone.id)] = milestone_node
                    for task in tasks:
                        prs = forge_map.get(("task", task.id), [])
                        pr = prs[0] if prs else None
                        task_links = vcs_map.get(("task", task.id), [])
                        leaf = milestone_node.add_leaf(
                            task_row(
                                task,
                                self.store,
                                links=[link.sha for link in task_links],
                                width=self._row_width(tree, 11),
                                pr_state=pr.state if pr else "",
                                pr_checks=pr.checks if pr else "",
                                stale=any(link.stale for link in task_links),
                            ),
                            data={"kind": "task", "id": task.id},
                        )
                        self._row_nodes[("task", task.id)] = leaf

        def _apply_folds(self) -> None:
            """Plans open to milestones, milestones to tasks, only when expanded."""
            try:
                for key, node in self._row_nodes.items():
                    if not node.allow_expand or not node.children:
                        continue
                    if key in self._expanded:
                        node.expand()
                    else:
                        node.collapse()
            finally:
                self._refreshing = False

        def _restore_selection(
            self, tree: Tree, prev_selected: tuple[str, int] | None, prev_cursor: Any
        ) -> None:
            """Keep the cursor on the same row across rebuilds."""
            target = prev_selected if prev_selected in self._row_nodes else prev_cursor
            if target not in self._row_nodes:
                target = None
            if target is None and self._row_nodes:
                for key in self._row_nodes:
                    if key[0] == "plan":
                        target = key
                        break
                if target is None:
                    target = next(iter(self._row_nodes))
                self.selected = target
            if target not in self._row_nodes:
                return
            node = self._row_nodes[target]
            try:
                tree.move_cursor(node)
            except Exception:
                pass

            def _restore(n: Any = node) -> None:
                try:
                    tree.move_cursor(n)
                    tree.scroll_to_node(n)
                except Exception:
                    pass

            try:
                self.call_after_refresh(_restore)
            except Exception:
                pass

        def refresh_all(self, note: str = "") -> None:
            tree = self.query_one("#tree", Tree)
            self._refreshing = True
            prev_selected = self.selected
            try:
                cursor = tree.cursor_node
                prev_cursor = self._node_key(cursor) if cursor is not None else None
            except Exception:
                prev_cursor = None
            tree.clear()
            self._row_nodes = {}
            progress = self._progress_map()
            filtered = self._filtered_tree()
            filtered.sort(key=lambda entry: entry[0].status == Status.DONE)
            self._build_rows(
                tree.root,
                tree,
                filtered,
                progress,
                self.store.forge_links_map(),
                self.store.vcs_links_map(),
                self._source_stats(),
            )
            tree.root.expand()
            self._collapsed &= set(self._row_nodes)
            self._expanded &= set(self._row_nodes)
            self._apply_folds()
            self.query_one("#status", Label).update(self._status_text(self.store.counts(), note))
            self.query_one("#hints", Label).update(hint_bar(max(10, self.size.width - 2)))
            self._restore_selection(tree, prev_selected, prev_cursor)
            self.update_preview()

        def action_refresh(self) -> None:
            self._saved("manual refresh")

        def _git_selection(self) -> tuple[str, int] | None:
            """Selected row for a git action, or a notification when none."""
            if self.selected is None:
                self.notify("select a row first", timeout=3)
                return None
            return self.selected

        def action_git_status(self) -> None:
            """Show branch and dirty state for the selected row's checkouts."""
            selected = self._git_selection()
            if selected is None:
                return
            kind, oid = selected
            try:
                entries = services.repo_statuses(self.store, kind, oid)
            except ValueError as exc:
                self.notify(str(exc), severity="error", timeout=5)
                return
            if not entries:
                self.notify("no linked repos", timeout=3)
                return
            self.notify(render_git_status(entries), timeout=8)
            self._pending_note = "git status"

        def action_git_refresh(self) -> None:
            """Re-resolve cached commits and mark stale links."""
            selected = self._git_selection()
            if selected is None:
                return
            kind, oid = selected
            result = services.refresh_links(self.store, kind, oid)
            self.notify(
                f"checked {result['checked']} links · "
                f"{result['updated']} updated · {result['stale']} stale",
                timeout=6,
            )
            self._saved("git links refreshed")

        def action_git_capture(self) -> None:
            """Link a safe current HEAD to the selected row."""
            selected = self._git_selection()
            if selected is None:
                return
            kind, oid = selected
            before = {link.sha for link in self.store.list_links(kind, oid)}
            repos = self.store.effective_repos(kind, oid)
            cwd = str(repos[0]["repo_path"]) if repos else "."
            reason = services.auto_capture_head(self.store, kind, oid, cwd=cwd)
            after = {link.sha for link in self.store.list_links(kind, oid)}
            if after - before:
                self.notify("HEAD linked", timeout=4)
                self._saved("commit linked")
                return
            if reason:
                self.notify(f"not linked: {reason}", severity="warning", timeout=6)
                return
            self.notify("HEAD is already linked or unavailable", timeout=4)

        def action_open_pr(self) -> None:
            """Open the first linked pull request in the default browser."""
            selected = self._git_selection()
            if selected is None:
                return
            kind, oid = selected
            links = self.store.effective_forge_links(kind, oid)
            url = next((link.url for link in links if link.url), "")
            if not url:
                self.notify("no pull request linked", timeout=3)
                return
            webbrowser.open(url)
            self.notify(f"opened {url}", timeout=4)

        def action_source_trail(self) -> None:
            """Open the read-only source trail for the selected row."""
            selected = self._git_selection()
            if selected is None:
                return
            kind, oid = selected
            self.push_screen(SourceScreen(self.store, kind, oid))

        def _saved(self, note: str = "") -> None:
            """Local mutation path: bump reactive rev, watch refreshes."""
            self._pending_note = note
            try:
                self.rev += 1
            except Exception:
                self._fp = self.store.fingerprint()
                self.refresh_all(note)

        def action_filter_status(self) -> None:
            i = STATUS_CYCLE.index(self.status_filter)
            self.status_filter = STATUS_CYCLE[(i + 1) % len(STATUS_CYCLE)]
            self.refresh_all(
                f"status filter: {self.status_filter.value if self.status_filter else 'all'}"
            )

        SOURCE_FILTERS = ("all", "linked", "pr", "stale", "unlinked")

        def action_filter_source(self) -> None:
            """Cycle cached provenance filters."""
            index = self.SOURCE_FILTERS.index(self.source_filter)
            self.source_filter = self.SOURCE_FILTERS[(index + 1) % len(self.SOURCE_FILTERS)]
            self.refresh_all(f"source filter: {self.source_filter}")

        def action_toggle_show_all(self) -> None:
            self.show_all = not self.show_all
            self.refresh_all("showing all plans" if self.show_all else "showing recent plans")

        def action_help(self) -> None:
            self.push_screen(HelpScreen())

        def _palette_context(self) -> dict[str, str | None]:
            """Disable commands that cannot run for the current selection."""
            selected = self.selected is not None
            plan_id = self._plan_ctx()
            milestone_id = self._milestone_for_task_ctx()
            context: dict[str, str | None] = {cmd.id: None for cmd in COMMANDS}
            if not selected:
                for cmd in COMMANDS:
                    if cmd.context == "selection":
                        context[cmd.id] = "Select a row first"
            if plan_id is None:
                context["create-milestone"] = "Select a plan first"
                context["export-plan"] = "Select a plan first"
            if milestone_id is None:
                context["create-task"] = "Select a milestone first"
            if self.selected is not None and self.selected[0] == "task":
                context["fold-one"] = "Nothing to fold"
            return context

        def action_command_palette(self) -> None:
            """Open the modal command palette (c)."""
            if len(self.screen_stack) > 1:
                return
            self.push_screen(PaletteScreen(self._palette_context()), self._run_palette_command)

        def action_filter_text(self) -> None:
            """Prompt for filter text (slash)."""
            self._open_filter_prompt()

        def _open_filter_prompt(self) -> None:
            """Prompt for tree filter text; empty clears the filter."""

            def cb(text: str | None) -> None:
                if text is None:
                    return
                self.filter_text = text
                self._pending_note = f"filter: {text}" if text else "filter cleared"
                try:
                    self.rev += 1
                except Exception:
                    self.refresh_all(self._pending_note)

            self.push_screen(FilterPromptScreen(), cb)

        def _run_palette_command(self, command_id: str | None) -> None:
            """Run one palette command id through the shared registry."""
            if not command_id:
                return
            command = by_id(command_id)
            if command is None:
                return
            handlers: dict[str, Any] = {
                "new_plan": self.action_new_plan,
                "new_milestone": self.action_new_milestone,
                "new_task": self.action_new_task,
                "add_criterion": self.action_add_criterion,
                "edit_selection": self.action_edit_selection,
                "move_todo": lambda: self.action_move(Status.TODO),
                "move_doing": lambda: self.action_move(Status.DOING),
                "move_done": lambda: self.action_move(Status.DONE),
                "tick_criterion": self.action_criteria,
                "untick_criterion": self.action_untick_criterion,
                "delete_selection": self.action_delete,
                "open_detail": self.action_open_detail,
                "fold": self.action_fold,
                "fold_all": self.action_fold_all,
                "filter_text": self.action_filter_text,
                "filter_status": self.action_filter_status,
                "filter_source": self.action_filter_source,
                "toggle_show_all": self.action_toggle_show_all,
                "refresh": self.action_refresh,
                "git_status": self.action_git_status,
                "git_refresh": self.action_git_refresh,
                "git_capture": self.action_git_capture,
                "open_pr": self.action_open_pr,
                "source_trail": self.action_source_trail,
                "command_palette": self.action_command_palette,
                "export_md": self.action_export_md,
                "help": self.action_help,
                "quit": self.exit,
            }
            fn = handlers.get(command.handler)
            if fn is None:
                return
            fn()
            self._pending_note = command.label.lower()

        # -- editing ------------------------------------------------------
        def _milestone_for_task_ctx(self) -> int | None:
            if self.selected is None:
                return None
            kind, oid = self.selected
            if kind == "milestone":
                return oid
            if kind == "task":
                t = self.store.get_task(oid)
                return t.milestone_id if t else None
            return None

        def _plan_ctx(self) -> int | None:
            if self.selected is None:
                return None
            kind, oid = self.selected
            if kind == "plan":
                return oid
            if kind == "milestone":
                s = self.store.get_milestone(oid)
                return s.plan_id if s else None
            if kind == "task":
                t = self.store.get_task(oid)
                if t is None:
                    return None
                s = self.store.get_milestone(t.milestone_id)
                return s.plan_id if s else None
            return None

        def _cursor_is_root(self) -> bool:
            """True when the cursor sits on the dataless plans root or empty tree."""
            try:
                tree = self.query_one("#tree", Tree)
            except Exception:
                return True
            try:
                cur = tree.cursor_node
            except Exception:
                return True
            if cur is None:
                return True
            return self._node_key(cur) is None

        def action_new_context(self) -> None:
            if self._cursor_is_root():
                self.action_new_plan()
                return
            sid = self._milestone_for_task_ctx()
            if sid is not None:
                self.action_new_task()
                return
            pid = self._plan_ctx()
            if pid is not None:
                self.action_new_milestone()
                return
            self.action_new_plan()

        def action_new_plan(self) -> None:
            def cb(data: dict | None) -> None:
                if not data:
                    return
                try:
                    services.create_plan(
                        self.store,
                        data["title"],
                        data["what"],
                        goal=data["why"],
                        actor="tui",
                    )
                except ValueError as exc:
                    self.notify(f"error: {exc}")
                self._saved("plan created")

            self.push_screen(
                NewPlanScreen(defaults=load_template("plan", self.store.path).defaults), cb
            )

        def action_new_milestone(self) -> None:
            pid = self._plan_ctx()
            if pid is None:
                self.notify("select a plan first (j/k + click)")
                return

            def cb(data: dict | None) -> None:
                if not data:
                    return
                try:
                    services.create_milestone(
                        self.store,
                        pid,
                        data["title"],
                        data["desc"],
                        actor="tui",
                    )
                except (ValueError, KeyError) as exc:
                    self.notify(f"error: {exc}")
                self._saved("milestone created")

            self.push_screen(
                NewMilestoneScreen(
                    pid,
                    defaults=load_template("milestone", self.store.path).defaults,
                    context=f"P{pid}",
                ),
                cb,
            )

        def action_new_task(self) -> None:
            sid = self._milestone_for_task_ctx()
            if sid is None:
                self.notify("select a milestone first (n on a plan creates one)")
                return

            def cb(data: dict | None) -> None:
                if not data:
                    return
                try:
                    services.create_task(
                        self.store,
                        sid,
                        data["title"],
                        data["desc"],
                        actor="tui",
                    )
                except (ValueError, KeyError) as exc:
                    self.notify(f"error: {exc}")
                self._saved("task created")

            milestone = self.store.get_milestone(sid)
            where = f"P{milestone.plan_id} › M{sid}" if milestone else f"M{sid}"
            self.push_screen(
                NewTaskScreen(
                    sid,
                    defaults=load_template("task", self.store.path).defaults,
                    context=where,
                ),
                cb,
            )

        def action_toggle_status(self) -> None:
            if self.selected is None:
                self.notify("select a row first (s advances status)")
                return
            kind, oid = self.selected
            left = self.store.open_criteria(kind, oid)
            current = self.store.get_parent(kind, oid)
            if left and (current is None or current.status != Status.DONE):
                # advisory only: warn, then proceed (flow first)
                self.notify(f"warning: {len(left)} open criteria — closing anyway", timeout=5)
            nxt = services.cycle_status(self.store, kind, oid, actor="tui")
            if nxt is None:
                self.notify("selected row no longer exists")
            self._saved(f"{kind} {oid} -> {nxt.value if nxt else '?'}")

        def action_move(self, status: Status) -> None:
            """Move the selection to an explicit status (palette)."""
            if self.selected is None:
                self.notify("select a row first, then move it")
                return
            kind, oid = self.selected
            left = self.store.open_criteria(kind, oid)
            if status == Status.DONE and left:
                self.notify(f"warning: {len(left)} open criteria — closing anyway", timeout=5)
            if not services.set_status(self.store, kind, oid, status, actor="tui"):
                self.notify("selected row no longer exists")
                return
            self._saved(f"{kind} {oid} -> {status.value}")

        def action_add_criterion(self) -> None:
            """Prompt for a new criterion on the selected row."""
            if self.selected is None:
                self.notify("select a row first (a adds a criterion)")
                return
            kind, oid = self.selected

            def cb(text: str | None) -> None:
                if not text:
                    return
                try:
                    self.store.add_criteria(kind, oid, text, actor="tui")
                except (ValueError, KeyError) as exc:
                    self.notify(f"error: {exc}")
                    return
                self._saved("criterion added")

            self.push_screen(
                FilterPromptScreen(
                    title=f"New criterion on {kind} {oid}",
                    placeholder="what must be true?",
                    submit_label="Add",
                ),
                cb,
            )

        def action_untick_criterion(self) -> None:
            """Reopen the last ticked criterion on the selected row."""
            if self.selected is None:
                self.notify("select a row first (x ticks criteria)")
                return
            kind, oid = self.selected
            done = [c for c in self.store.list_criteria(kind, oid) if c.done]
            if not done:
                self.notify("no ticked criteria to reopen")
                return
            target = done[-1]
            self.store.set_criteria(target.id, False, actor="tui")
            self._saved(f"criterion #{target.id} reopened")

        def action_edit_selection(self) -> None:
            """Edit the selected row; detail owns the edit form."""
            if self.selected is None:
                self.notify("select a row first (e edits it)")
                return
            self._open_detail(*self.selected, edit=True)

        async def action_quit(self) -> None:
            """Leave the screen (q)."""
            self.exit()

        def action_criteria(self) -> None:
            """Tick first open criterion; if none open, reopen the last done one."""
            if self.selected is None:
                self.notify("select a row first (x ticks criteria)")
                return
            kind, oid = self.selected
            items = self.store.list_criteria(kind, oid)
            if not items:
                self.notify(
                    f'no criteria — add via: lpui add-criteria --kind {kind} --id {oid} --text "..."'
                )
                return
            open_items = [c for c in items if not c.done]
            if open_items:
                target, reopen = open_items[0], False
            else:
                target, reopen = items[-1], True  # nothing open: re-affirm by reopening last
            self.store.set_criteria(target.id, not reopen, actor="tui")
            verb = "reopened" if reopen else "checked"
            self._saved(f"criterion {target.id} {verb}")

        def action_delete(self) -> None:
            if self.selected is None:
                self.notify("select a row first (d deletes with confirm)")
                return
            kind, oid = self.selected

            def cb(confirmed: bool | None) -> None:
                if not confirmed:
                    return
                if not self.store.delete(kind, oid, actor="tui"):
                    self.notify("already gone — refreshing")
                self.selected = None
                self._saved(f"deleted {kind} #{oid}")

            self.push_screen(ConfirmScreen(f"Delete {kind} #{oid}?\n(children go too.)"), cb)

        def on_tree_node_selected(self, e: Tree.NodeSelected) -> None:
            """Clicks and cursor moves select only; enter/double-click open detail."""
            self._track(e.node)

        def note_click(self, key: tuple[str, int]) -> bool:
            """True when this click completes a double-click on the same row."""
            now = time.monotonic()
            double = (
                key == self._last_click_key and (now - self._last_click_at) < DOUBLE_CLICK_WINDOW
            )
            self._last_click_key, self._last_click_at = key, now
            return double

        def _open_detail(self, kind: str, oid: int, edit: bool = False) -> None:
            def cb(saved: bool | None) -> None:
                if saved:
                    self._saved("saved detail")

            self.push_screen(DetailScreen(self.store, kind, oid, edit=edit), cb)

        def action_export_md(self) -> None:
            pid = self._plan_ctx()
            if pid is None:
                self.notify("select a row first, then export")
                return
            entry = services.export_plan(self.store, pid)
            if entry is None:
                self.notify("selected plan no longer exists — refreshing")
                self.refresh_all("")
                return
            from .render import render_plan_markdown

            path = f"plan-P{pid}.md"
            with open(path, "w") as fh:
                fh.write(render_plan_markdown(entry) + "\n")
            self._saved(f"exported {path}")

        def action_open_detail(self) -> None:
            if len(self.screen_stack) > 1:
                return  # a modal owns enter
            if self.selected is None:
                self.notify("select a row first, then enter")
                return
            self._open_detail(*self.selected)

    def create_app(db_path: str | None = None) -> LazyplanApp:
        """Build the app bound to a store."""
        return LazyplanApp(Store(db_path))


def run(db_path: str | None = None) -> int:
    """Run the TUI; exit 3 when Textual is missing."""
    if not _TEXTUAL_OK:
        print("Textual not installed. Run: pip install -e . then: lpui ui")
        print("Fallback (no TUI): lpui list")
        return 3
    create_app(db_path).run()
    return 0
