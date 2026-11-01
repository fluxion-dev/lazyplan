"""Tree loading, filtering, folding, and selection restoration."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from textual.widgets import Label, Static, Tree
from textual.widgets.tree import TreeNode

from ... import services
from ...design import milestone_row, plan_row, status_prefix, task_row
from ...help import hint_bar
from ...models import Milestone, Plan, Status, Task
from ..views.rows import row_text
from .filtering import TreeFilter

if TYPE_CHECKING:
    from ..app import LazyplanApp


class TreeController:
    """Owns the plan tree model and the row cache."""

    def __init__(self, app: LazyplanApp) -> None:
        self.app = app
        self.filters = TreeFilter(app)

    @staticmethod
    def node_key(node: TreeNode) -> tuple[str, int] | None:
        data = getattr(node, "data", None)
        if isinstance(data, dict) and "kind" in data and "id" in data:
            return (str(data["kind"]), int(data["id"]))
        return None

    def track(self, node: TreeNode) -> None:
        data = getattr(node, "data", None)
        if isinstance(data, dict) and "kind" in data and "id" in data:
            self.app.selected = (data["kind"], int(data["id"]))
            self.app.update_preview()
            self.app.metrics_controller.request()

    def apply_folds(self) -> None:
        """Plans open to milestones, milestones to tasks, only when expanded."""
        try:
            for key, node in self.app._row_nodes.items():
                if not node.allow_expand or not node.children:
                    continue
                if key in self.app._expanded:
                    node.expand()
                else:
                    node.collapse()
        finally:
            self.app._refreshing = False

    def fold_all(self) -> None:
        """Collapse every expandable row, or re-open all when fully expanded."""
        keys = [
            key for key, node in self.app._row_nodes.items() if node.allow_expand and node.children
        ]
        if not keys:
            self.app.notify("nothing to fold")
            return
        if all(key in self.app._expanded for key in keys):
            for key in keys:
                self.app._row_nodes[key].collapse()
            self.app._expanded.clear()
            self.app._collapsed.update(keys)
            return
        for key in keys:
            self.app._row_nodes[key].expand()
        self.app._expanded.update(keys)
        self.app._collapsed.difference_update(keys)

    def fold_one(self) -> None:
        """Toggle the selected plan or milestone (z)."""
        if self.app.selected is None:
            self.app.notify("select a row first (z folds it)")
            return
        node = self.app._row_nodes.get(self.app.selected)
        if node is None or not node.allow_expand or not node.children:
            self.app.notify("nothing to fold here")
            return
        key = self.app.selected
        if key in self.app._expanded:
            node.collapse()
            self.app._expanded.discard(key)
            self.app._collapsed.add(key)
            return
        node.expand()
        self.app._expanded.add(key)
        self.app._collapsed.discard(key)

    def poll(self) -> None:
        """External-change detector; local edits go through the reactive rev."""
        app = self.app
        if app._dirty_external and len(app.screen_stack) <= 1:
            app._dirty_external = False
            app.rev += 1
            return
        try:
            fingerprint = app.store.fingerprint()
        except Exception:
            return
        if fingerprint == app._fp:
            return
        app._fp = fingerprint
        events = app.store.feed(1)
        note = "db changed — refreshed"
        if events:
            event = events[0]
            note = f"[{event['actor']}] {event['kind']}/{event['action']}: {event['detail']}"
            try:
                app.notify(note, timeout=4)
            except Exception:
                pass
        app._pending_note = note
        if len(app.screen_stack) > 1:
            app._dirty_external = True
            return
        app.rev += 1

    def restore_selection(
        self,
        tree: Tree,
        prev_selected: tuple[str, int] | None,
        prev_cursor: Any,
    ) -> None:
        """Keep the cursor on the same row across rebuilds."""
        app = self.app
        target = prev_selected if prev_selected in app._row_nodes else prev_cursor
        if target not in app._row_nodes:
            target = None
        if target is None and app._row_nodes:
            for key in app._row_nodes:
                if key[0] == "plan":
                    target = key
                    break
            if target is None:
                target = next(iter(app._row_nodes))
            app.selected = target
        if target not in app._row_nodes:
            return
        node = app._row_nodes[target]
        try:
            tree.move_cursor(node)
        except Exception:
            pass

        def _restore(cursor: Any = node) -> None:
            try:
                tree.move_cursor(cursor)
                tree.scroll_to_node(cursor)
            except Exception:
                pass

        try:
            app.call_after_refresh(_restore)
        except Exception:
            pass

    @staticmethod
    def progress_map(
        base: list[tuple[Plan, list[tuple[Milestone, list[Task]]]]],
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

    def paint_mark(self, key: tuple[str, int]) -> None:
        """Add or remove the mark glyph on one existing row."""
        app = self.app
        label = app._row_labels.get(key)
        node = app._row_nodes.get(key)
        if label is None or node is None:
            return
        if key in app.spinner_controller.rows:
            label = (
                status_prefix(Status.DOING, app.spinner_controller.tick)
                + app.spinner_controller.rows[key]
            )
        suffix = " [bold green]✓[/]" if key in app.marked else ""
        node.set_label(row_text(label + suffix))

    def row_width(self, tree: Tree, depth: int) -> int:
        """Usable label width for a row at `depth`, excluding tree guides."""
        app = self.app
        base = tree.size.width or (
            max(20, app.size.width // 2) if app.size.width >= 100 else max(20, app.size.width)
        )
        return max(10, base - 5 - depth)

    def show_empty(self, empty: bool) -> None:
        """Swap the tree for the centered empty state when no rows are visible."""
        tree = self.app.query_one("#tree", Tree)
        was_empty = not tree.display
        tree.display = not empty
        self.app.query_one("#tree-empty", Static).display = empty
        if was_empty and not empty and len(self.app.screen_stack) <= 1:
            tree.focus()

    def refresh_all(self, note: str = "") -> None:
        app = self.app
        tree = app.query_one("#tree", Tree)
        app._refreshing = True
        prev_selected = app.selected
        try:
            cursor = tree.cursor_node
            prev_cursor = self.node_key(cursor) if cursor is not None else None
        except Exception:
            prev_cursor = None
        tree.clear()
        app._row_nodes = {}
        app._row_labels = {}
        app.spinner_controller.rows = {}
        base = services.tree(app.store, status=None, archived="hide")
        progress = self.progress_map(base)
        visible = self.filters.status_tree(base, app.status_filter)
        if not (app.show_all or app.filter_text.strip()):
            visible = visible[: services.DEFAULT_PLAN_LIMIT]
        filtered = self.filters.filtered_tree(visible)
        filtered.sort(key=lambda entry: entry[0].status == Status.DONE)
        self.build_rows(
            tree.root,
            tree,
            filtered,
            progress,
            app.store.forge_links_map(),
            app.store.vcs_links_map(),
            self.filters.source_stats(filtered),
            app.store.claims_map(),
        )
        tree.root.expand()
        app._collapsed &= set(app._row_nodes)
        app._expanded &= set(app._row_nodes)
        self.apply_folds()
        self.show_empty(not app._row_nodes)
        app.spinner_controller.paint()
        app.query_one("#hints", Label).update(hint_bar(max(10, app.size.width - 2), markup=True))
        self.restore_selection(tree, prev_selected, prev_cursor)
        app.metrics_controller.refresh()
        app._preview_key = None
        app.update_preview(force=True)

    def on_expanded(self, node: TreeNode) -> None:
        if self.app._refreshing:
            return
        key = self.node_key(node)
        if key is not None:
            self.app._collapsed.discard(key)
            if key[0] in ("plan", "milestone"):
                self.app._expanded.add(key)

    def on_collapsed(self, node: TreeNode) -> None:
        if self.app._refreshing:
            return
        key = self.node_key(node)
        if key is not None and key[0] in ("plan", "milestone"):
            self.app._collapsed.add(key)
            self.app._expanded.discard(key)

    def build_rows(
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
        app = self.app
        for plan, milestones in filtered:
            plan_stats = source_stats.get(("plan", plan.id))
            plan_text = plan_row(
                plan,
                progress=progress.get(("plan", plan.id)),
                width=self.row_width(tree, 3),
                source_counts=(
                    (plan_stats[0], plan_stats[1], plan_stats[2]) if plan_stats else None
                ),
                marked=("plan", plan.id) in app.marked,
            )
            plan_node = root.add(
                row_text(plan_text),
                data={"kind": "plan", "id": plan.id},
                allow_expand=bool(milestones),
            )
            app._row_nodes[("plan", plan.id)] = plan_node
            app._row_labels[("plan", plan.id)] = plan_text
            app.spinner_controller.remember(("plan", plan.id), plan.status, plan_text)
            for milestone, tasks in milestones:
                milestone_stats = source_stats.get(("milestone", milestone.id))
                milestone_text = milestone_row(
                    milestone,
                    app.store,
                    progress=progress.get(("milestone", milestone.id)),
                    width=self.row_width(tree, 7),
                    source_counts=(
                        (
                            milestone_stats[0],
                            milestone_stats[1],
                            milestone_stats[2],
                        )
                        if milestone_stats
                        else None
                    ),
                    marked=("milestone", milestone.id) in app.marked,
                )
                milestone_node = plan_node.add(
                    row_text(milestone_text),
                    data={"kind": "milestone", "id": milestone.id},
                    allow_expand=bool(tasks),
                )
                app._row_nodes[("milestone", milestone.id)] = milestone_node
                app._row_labels[("milestone", milestone.id)] = milestone_text
                app.spinner_controller.remember(
                    ("milestone", milestone.id), milestone.status, milestone_text
                )
                for task in tasks:
                    prs = forge_map.get(("task", task.id), [])
                    pr = prs[0] if prs else None
                    task_links = vcs_map.get(("task", task.id), [])
                    task_text = task_row(
                        task,
                        app.store,
                        links=[link.sha for link in task_links],
                        width=self.row_width(tree, 11),
                        pr_state=pr.state if pr else "",
                        pr_checks=pr.checks if pr else "",
                        stale=any(link.stale for link in task_links),
                        claim_actor=(claims_map[task.id].actor if task.id in claims_map else ""),
                        claim_expired=(
                            claims_map[task.id].expired(time.time())
                            if task.id in claims_map
                            else False
                        ),
                        blocked=task.blocked,
                        marked=("task", task.id) in app.marked,
                    )
                    leaf = milestone_node.add_leaf(
                        row_text(task_text),
                        data={"kind": "task", "id": task.id},
                    )
                    app._row_nodes[("task", task.id)] = leaf
                    app._row_labels[("task", task.id)] = task_text
                    app.spinner_controller.remember(("task", task.id), task.status, task_text)
