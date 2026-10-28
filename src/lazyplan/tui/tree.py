"""Textual tree widget and tree mixin."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, cast

try:
    from textual import events, on  # noqa: F401
    from textual.app import App, ComposeResult  # noqa: F401
    from textual.binding import Binding  # noqa: F401
    from textual.containers import Horizontal, Vertical, VerticalScroll  # noqa: F401
    from textual.reactive import reactive  # noqa: F401
    from textual.widgets import Label, Static, Tree  # noqa: F401
    from textual.widgets.tree import TreeNode  # noqa: F401

    from ..tree_nav import NavTree  # noqa: F401

    _TEXTUAL_OK = True
except ImportError:  # pragma: no cover
    _TEXTUAL_OK = False

from .. import services
from ..design import (
    milestone_row,
    plan_row,
    status_prefix,
    task_row,
)
from ..help import hint_bar
from ..messages import RowAction, SelectionChanged
from ..models import Milestone, Plan, Status, Task
from .base import AppBase

if TYPE_CHECKING:
    from .app import LazyplanApp
STATUS_CYCLE: list[Status | None] = [None, Status.TODO, Status.DOING, Status.DONE]
DOUBLE_CLICK_WINDOW = 0.5  # seconds between two clicks on one row


if _TEXTUAL_OK:

    class FoldTree(NavTree):
        """Plan/milestone tree: j/k + arrows move, left/right fold, enter opens.

        Every mutation runs through the modal palette (c). Native Tree
        Space marks the selected row for bulk actions; shift+space stays parked.
        Status and folding continue to live in the palette and shared gestures.
        """

        BINDINGS = [
            Binding("enter", "open_detail", "Detail"),
            Binding("space", "toggle_mark", "Mark"),
        ]

        def on_tree_node_highlighted(self, e: Tree.NodeHighlighted) -> None:
            """Bubble selection as a custom message (guide/events pattern)."""
            key = TreeMixin._node_key(e.node)
            if key is not None:
                self.post_message(SelectionChanged(kind=key[0], oid=key[1]))

        def action_toggle_mark(self) -> None:
            """Space: mark or unmark the selected row."""
            cast("LazyplanApp", self.app).action_toggle_mark()

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
            """Single click selects; two quick clicks on one row open detail.

            Textual dispatches `_on_click` for every class in the MRO, so the
            base Tree handler still runs after this one. Do not call super()
            here or an arrow click would toggle twice and appear to do nothing.
            """
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
            key = TreeMixin._node_key(node)
            if key is None:
                return
            # Messages-up: announce selection, then open on double-click.
            self.post_message(SelectionChanged(kind=key[0], oid=key[1]))
            if app.note_click(key):
                self.post_message(RowAction("open-detail", key[0], key[1]))

    class TreeMixin(AppBase):
        """Tree loading, folding, and refresh."""

        def on_tree_node_selected(self, e: Tree.NodeSelected) -> None:
            """Clicks and cursor moves select only; enter/double-click open detail."""
            self._track(e.node)

        def _track(self, node: TreeNode) -> None:
            data = getattr(node, "data", None)
            if isinstance(data, dict) and "kind" in data and "id" in data:
                self.selected = (data["kind"], int(data["id"]))
                self.update_preview()

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
                self._refresh_status(f"folded {len(keys)} rows")
            else:
                for k in keys:
                    self._row_nodes[k].expand()
                self._expanded.update(keys)
                self._collapsed.difference_update(keys)
                self._refresh_status("unfolded all")

        def _poll(self) -> None:
            """External-change detector; local edits go through rev."""
            if self._dirty_external and len(self.screen_stack) <= 1:
                self._dirty_external = False
                self.rev += 1
                return
            try:
                fp = self.store.fingerprint()
            except Exception:
                return
            if fp != self._fp:
                self._fp = fp
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
                if len(self.screen_stack) > 1:
                    self._dirty_external = True
                    return
                self.rev += 1

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

        @staticmethod
        def _node_key(node: TreeNode) -> tuple[str, int] | None:
            data = getattr(node, "data", None)
            if isinstance(data, dict) and "kind" in data and "id" in data:
                return (str(data["kind"]), int(data["id"]))
            return None

        def _progress_map(
            self, base: list[tuple[Plan, list[tuple[Milestone, list[Task]]]]]
        ) -> dict[tuple[str, int], tuple[int, int]]:
            """Task progress per plan and milestone from one unfiltered snapshot."""
            out: dict[tuple[str, int], tuple[int, int]] = {}
            for plan, milestones in base:
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

        def _paint_mark(self, key: tuple[str, int]) -> None:
            """Add or remove the mark glyph on one existing row."""
            label = self._row_labels.get(key)
            node = self._row_nodes.get(key)
            if label is None or node is None:
                return
            if key in self._spinner_rows:
                label = status_prefix(Status.DOING, self._spinner_tick) + self._spinner_rows[key]
            suffix = " [bold green]✓[/]" if key in self.marked else ""
            node.set_label(label + suffix)

        def on_tree_node_highlighted(self, e: Tree.NodeHighlighted) -> None:
            self._track(e.node)

        def _row_width(self, tree: Tree, depth: int) -> int:
            """Usable label width for a row at `depth`, excluding tree guides."""
            base = tree.size.width or (
                max(20, self.size.width // 2)
                if self.size.width >= 100
                else max(20, self.size.width)
            )
            return max(10, base - 5 - depth)

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
                self._refresh_status(f"{key[0]} {key[1]} folded")
            else:
                node.expand()
                self._expanded.add(key)
                self._collapsed.discard(key)
                self._refresh_status(f"{key[0]} {key[1]} unfolded")

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
            self._row_labels = {}
            self._spinner_rows = {}
            base = services.tree(self.store, status=None, archived="hide")
            progress = self._progress_map(base)
            visible = self._status_tree(base, self.status_filter)
            if not (self.show_all or self.filter_text.strip()):
                visible = visible[: services.DEFAULT_PLAN_LIMIT]
            filtered = self._filtered_tree(visible)
            filtered.sort(key=lambda entry: entry[0].status == Status.DONE)
            self._build_rows(
                tree.root,
                tree,
                filtered,
                progress,
                self.store.forge_links_map(),
                self.store.vcs_links_map(),
                self._source_stats(filtered),
                self.store.claims_map(),
            )
            tree.root.expand()
            self._collapsed &= set(self._row_nodes)
            self._expanded &= set(self._row_nodes)
            self._apply_folds()
            self._paint_spinner()
            self.query_one("#status", Label).update(self._status_text(self.store.counts(), note))
            self.query_one("#hints", Label).update(hint_bar(max(10, self.size.width - 2)))
            self._restore_selection(tree, prev_selected, prev_cursor)
            self._preview_key = None
            self.update_preview(force=True)

        def on_tree_node_expanded(self, e: Tree.NodeExpanded) -> None:
            if self._refreshing:
                return
            key = self._node_key(e.node)
            if key is not None:
                self._collapsed.discard(key)
                if key[0] in ("plan", "milestone"):
                    self._expanded.add(key)

        def _build_rows(
            self,
            root: Any,
            tree: Tree,
            filtered: list,
            progress: dict,
            forge_map: dict,
            vcs_map: dict,
            source_stats: dict,
            claims_map: dict,
        ) -> None:
            """Create plan/milestone/task nodes for one refresh."""
            for plan, milestones in filtered:
                plan_stats = source_stats.get(("plan", plan.id))
                plan_text = plan_row(
                    plan,
                    progress=progress.get(("plan", plan.id)),
                    width=self._row_width(tree, 3),
                    source_counts=(
                        (plan_stats[0], plan_stats[1], plan_stats[2]) if plan_stats else None
                    ),
                    repo_count=plan_stats[3] if plan_stats else 0,
                    marked=("plan", plan.id) in self.marked,
                )
                plan_node = root.add(
                    plan_text,
                    data={"kind": "plan", "id": plan.id},
                    allow_expand=bool(milestones),
                )
                self._row_nodes[("plan", plan.id)] = plan_node
                self._row_labels[("plan", plan.id)] = plan_text
                self._remember_spinner(("plan", plan.id), plan.status, plan_text)
                for milestone, tasks in milestones:
                    milestone_stats = source_stats.get(("milestone", milestone.id))
                    milestone_text = milestone_row(
                        milestone,
                        self.store,
                        progress=progress.get(("milestone", milestone.id)),
                        width=self._row_width(tree, 7),
                        source_counts=(
                            (
                                milestone_stats[0],
                                milestone_stats[1],
                                milestone_stats[2],
                            )
                            if milestone_stats
                            else None
                        ),
                        repo_count=milestone_stats[3] if milestone_stats else 0,
                        marked=("milestone", milestone.id) in self.marked,
                    )
                    milestone_node = plan_node.add(
                        milestone_text,
                        data={"kind": "milestone", "id": milestone.id},
                        allow_expand=bool(tasks),
                    )
                    self._row_nodes[("milestone", milestone.id)] = milestone_node
                    self._row_labels[("milestone", milestone.id)] = milestone_text
                    self._remember_spinner(
                        ("milestone", milestone.id), milestone.status, milestone_text
                    )
                    for task in tasks:
                        prs = forge_map.get(("task", task.id), [])
                        pr = prs[0] if prs else None
                        task_links = vcs_map.get(("task", task.id), [])
                        task_stats = source_stats.get(("task", task.id))
                        task_text = task_row(
                            task,
                            self.store,
                            links=[link.sha for link in task_links],
                            width=self._row_width(tree, 11),
                            pr_state=pr.state if pr else "",
                            pr_checks=pr.checks if pr else "",
                            stale=any(link.stale for link in task_links),
                            repo_count=task_stats[3] if task_stats else 0,
                            claim_actor=(
                                claims_map[task.id].actor if task.id in claims_map else ""
                            ),
                            claim_expired=(
                                claims_map[task.id].expired(time.time())
                                if task.id in claims_map
                                else False
                            ),
                            blocked=task.blocked,
                            marked=("task", task.id) in self.marked,
                        )
                        leaf = milestone_node.add_leaf(
                            task_text,
                            data={"kind": "task", "id": task.id},
                        )
                        self._row_nodes[("task", task.id)] = leaf
                        self._row_labels[("task", task.id)] = task_text
                        self._remember_spinner(("task", task.id), task.status, task_text)

        def on_tree_node_collapsed(self, e: Tree.NodeCollapsed) -> None:
            """Remember mouse folds across refreshes/polls."""
            if self._refreshing:
                return
            key = self._node_key(e.node)
            if key is not None and key[0] in ("plan", "milestone"):
                self._collapsed.add(key)
                self._expanded.discard(key)
