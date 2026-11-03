"""Tree loading, filtering, folding, and selection restoration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from textual.widgets import Label, Static, Tree
from textual.widgets.tree import TreeNode

from .... import services
from ....core.entities import Milestone, Plan, Status, Task
from ...shared.design import apply_mark, status_prefix
from ...shared.help import hint_bar
from ..views.rows import RowSpec, milestone_spec, plan_spec, row_text, task_spec
from .filtering import TreeFilter

if TYPE_CHECKING:
    from ..app import LazyplanApp
    from ..widgets.plan_tree import FoldTree


class TreeController:
    """Owns the plan tree model and the row cache."""

    def __init__(self, app: LazyplanApp) -> None:
        self.app = app
        self.filters = TreeFilter(app)
        self._reflow_pending = False

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
        """Update the fixed mark slot on one existing row."""
        app = self.app
        base = app._row_labels.get(key)
        node = app._row_nodes.get(key)
        if base is None or node is None:
            return
        marked = key in app.marked
        spinner = app.spinner_controller
        if key in spinner.rows:
            frame = spinner.tick if spinner.enabled else None
            label = status_prefix(Status.DOING, frame) + apply_mark(spinner.rows[key], marked)
        else:
            label = apply_mark(base, marked)
        node.set_label(row_text(label))

    def row_width(self, tree: Tree, depth: int) -> int:
        """Usable label width for a row at `depth`, excluding tree guides."""
        app = self.app
        base = tree.size.width or (
            max(20, app.size.width // 2) if app.size.width >= 100 else max(20, app.size.width)
        )
        return max(10, base - 5 - depth)

    def request_reflow(self) -> None:
        """Schedule one reflow after the next layout pass."""
        if self._reflow_pending:
            return
        self._reflow_pending = True
        self.app.call_after_refresh(lambda: self.app.call_after_refresh(self._run_reflow))

    def _run_reflow(self) -> None:
        self._reflow_pending = False
        if self.app._mounted:
            self.reflow()

    def reflow(self) -> None:
        """Rewrite existing rows at the current tree width without reloading."""
        app = self.app
        tree = cast("FoldTree", app.query_one("#tree", Tree))
        if not app._row_specs:
            return
        app.spinner_controller.rows = {}
        for key, spec in app._row_specs.items():
            self.render_row(key, spec, tree)
        for key in app._row_specs:
            self.paint_mark(key)
        tree.reflow()

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
        app._row_specs = {}
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

    def render_row(self, key: tuple[str, int], spec: RowSpec, tree: Tree) -> str:
        """Render and cache one row at the current tree width."""
        text = spec.markup(self.row_width(tree, spec.depth))
        self.app._row_labels[key] = text
        self.app.spinner_controller.remember(key, spec.status, text)
        return text

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
            plan_key = ("plan", plan.id)
            plan_row_spec = plan_spec(plan, progress, source_stats)
            app._row_specs[plan_key] = plan_row_spec
            plan_text = self.render_row(plan_key, plan_row_spec, tree)
            plan_node = root.add(
                row_text(apply_mark(plan_text, plan_key in app.marked)),
                data={"kind": "plan", "id": plan.id},
                allow_expand=bool(milestones),
            )
            app._row_nodes[plan_key] = plan_node
            for milestone, tasks in milestones:
                milestone_key = ("milestone", milestone.id)
                milestone_row_spec = milestone_spec(milestone, app.store, progress, source_stats)
                app._row_specs[milestone_key] = milestone_row_spec
                milestone_text = self.render_row(milestone_key, milestone_row_spec, tree)
                milestone_node = plan_node.add(
                    row_text(apply_mark(milestone_text, milestone_key in app.marked)),
                    data={"kind": "milestone", "id": milestone.id},
                    allow_expand=bool(tasks),
                )
                app._row_nodes[milestone_key] = milestone_node
                for task in tasks:
                    task_key = ("task", task.id)
                    task_row_spec = task_spec(task, app.store, forge_map, vcs_map, claims_map)
                    app._row_specs[task_key] = task_row_spec
                    task_text = self.render_row(task_key, task_row_spec, tree)
                    leaf = milestone_node.add_leaf(
                        row_text(apply_mark(task_text, task_key in app.marked)),
                        data={"kind": "task", "id": task.id},
                    )
                    app._row_nodes[task_key] = leaf
