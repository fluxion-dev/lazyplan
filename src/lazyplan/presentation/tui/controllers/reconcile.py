"""In-place tree reconciliation and view preservation.

Split from ``tree.py`` so the controller stays inside the module budget. The
mixin diffs one parent's children, relabels only changed rows, prunes caches
for removed subtrees, and restores the cursor, scroll, and focus afterwards.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from textual.widgets import Tree
from textual.widgets.tree import TreeNode

from ..views.rows import RowSpec, milestone_spec, plan_spec, row_text, task_spec

if TYPE_CHECKING:
    from ..app import LazyplanApp


class ReconcileMixin:
    """Reconcile tree rows in place and put the view back where it was."""

    app: LazyplanApp
    _loaded: set[tuple[str, int]]
    _model_keys: set[tuple[str, int]]
    _visible_keys: set[tuple[str, int]]
    _by_plan: dict
    _tasks_by_milestone: dict
    _claims_map: dict
    _progress: dict
    _attention: set[tuple[str, int]]

    if TYPE_CHECKING:

        def trees(self) -> tuple[Tree, Tree]: ...

        def node_key(self, node: TreeNode) -> tuple[str, int] | None: ...

        def row_width(self, tree: Tree, depth: int) -> int: ...

        def render_row(self, key: tuple[str, int], spec: RowSpec, tree: Tree) -> str: ...

        def load_branch(self, node: TreeNode, key: tuple[str, int]) -> None: ...

    def capture_view(self) -> dict[str, Any]:
        """Remember the cursor row, its ancestors, focus, and scroll offsets."""
        view: dict[str, Any] = {"cursor": None, "ancestors": [], "focus": None, "scroll": {}}
        for tree in self.trees():
            view["scroll"][tree.id] = (tree.scroll_x, tree.scroll_y)
            if tree.has_focus:
                view["focus"] = tree.id
                cursor = tree.cursor_node
                if cursor is not None:
                    view["cursor"] = self.node_key(cursor)
                    view["ancestors"] = self.ancestor_keys(cursor)
        return view

    def ancestor_keys(self, node: TreeNode) -> list[tuple[str, int]]:
        """Keys from a node's nearest parent up to the root, hidden rows included."""
        keys: list[tuple[str, int]] = []
        parent = node.parent
        while parent is not None:
            key = self.node_key(parent)
            if key is not None:
                keys.append(key)
            parent = parent.parent
        return keys

    def is_visible(self, node: TreeNode) -> bool:
        """True when the row's tree and every ancestor are open."""
        if not node.tree.display:
            return False
        parent = node.parent
        while parent is not None:
            if not parent.is_expanded:
                return False
            parent = parent.parent
        return True

    def visible_key(self, key: tuple[str, int]) -> tuple[str, int] | None:
        """The row itself or its nearest visible ancestor; never opens a branch."""
        node = self.app._row_nodes.get(key)
        while node is not None:
            if self.is_visible(node):
                return self.node_key(node)
            node = node.parent
        return None

    def restore_view(self, view: dict[str, Any], prev_selected: tuple[str, int] | None) -> None:
        """Restore cursor, scroll, and focus without opening a closed branch."""
        app = self.app
        candidates = [view.get("cursor"), prev_selected, *(view.get("ancestors") or [])]
        target: tuple[str, int] | None = None
        for candidate in candidates:
            if candidate is None or candidate not in app._row_nodes:
                continue
            target = self.visible_key(candidate)
            if target is not None:
                break
        if target is None:
            target = self.fallback_key()
        if target is None:
            return
        selected = app.selected
        if selected not in app._row_nodes or not self.is_visible(app._row_nodes[selected]):
            app.selected = target
        try:
            app.call_after_refresh(lambda: self._place_view(view, target))
        except Exception:
            pass

    def fallback_key(self) -> tuple[str, int] | None:
        """First visible plan row, else the first visible row of any kind."""
        visible = [
            (key, node) for key, node in self.app._row_nodes.items() if self.is_visible(node)
        ]
        for key, _node in visible:
            if key[0] == "plan":
                return key
        return visible[0][0] if visible else None

    def _place_view(
        self,
        view: dict[str, Any],
        target: tuple[str, int],
        attempt: int = 0,
    ) -> None:
        """Apply the saved offsets, then scroll only if the cursor is off-screen."""
        app = self.app
        node = app._row_nodes.get(target)
        if node is not None and node._line < 0 and attempt < 3:
            app.call_after_refresh(lambda: self._place_view(view, target, attempt + 1))
            return
        for tree in self.trees():
            x, y = view["scroll"].get(tree.id, (tree.scroll_x, tree.scroll_y))
            try:
                tree.scroll_to(x=x, y=y, animate=False)
            except Exception:
                pass
            if node is None or node.tree is not tree or node._line < 0:
                continue
            try:
                tree.cursor_line = node._line
            except Exception:
                continue
            height = max(1, tree.scrollable_content_region.height)
            if node._line < y or node._line >= y + height:
                try:
                    tree.scroll_to_node(node, animate=False)
                except Exception:
                    pass

    def add_row(
        self,
        parent: TreeNode[Any],
        tree: Tree,
        key: tuple[str, int],
        spec: RowSpec,
        allow_expand: bool,
    ) -> TreeNode[Any]:
        """Create one row under *parent* and index it in the caches."""
        app = self.app
        app._row_specs[key] = spec
        text = self.render_row(key, spec, tree)
        node = parent.add(
            row_text(text),
            data={"kind": key[0], "id": key[1]},
            allow_expand=allow_expand,
        )
        app._row_nodes[key] = node
        return node

    def update_row(
        self,
        node: TreeNode,
        key: tuple[str, int],
        spec: RowSpec,
        tree: Tree,
    ) -> bool:
        """Relabel one surviving row; return True when its text changed."""
        app = self.app
        app._row_specs[key] = spec
        text = spec.markup(self.row_width(tree, spec.depth))
        app.spinner_controller.remember(key, spec.status, text)
        if app._row_labels.get(key) == text:
            return False
        app._row_labels[key] = text
        node.set_label(row_text(text))
        return True

    def forget_subtree(self, node: TreeNode) -> None:
        """Drop every cache entry for a node and its descendants."""
        for child in list(node.children):
            self.forget_subtree(child)
        key = self.node_key(node)
        if key is None:
            return
        if self.app._row_nodes.get(key) is not node:
            return
        self.app._row_nodes.pop(key, None)
        self.app._row_specs.pop(key, None)
        self.app._row_labels.pop(key, None)
        self.app.spinner_controller.rows.pop(key, None)
        self._loaded.discard(key)

    def reconcile_children(
        self,
        parent: Any,
        tree: Tree,
        desired: list[tuple[tuple[str, int], RowSpec, bool]],
    ) -> set[tuple[str, int]]:
        """Update one parent's children in place; return the changed keys.

        Rows before the first order divergence keep their node object and are
        relabelled only when their text changed. Everything from that index is
        removed and re-added in the new order, so expansion state for the
        recreated rows is restored from the saved keys.
        """
        existing = list(parent.children)
        existing_keys = [self.node_key(node) for node in existing]
        wanted = [item[0] for item in desired]
        first = min(len(existing_keys), len(wanted))
        for index in range(first):
            if existing_keys[index] != wanted[index]:
                first = index
                break
        changed: set[tuple[str, int]] = set()
        for node in existing[first:]:
            key = self.node_key(node)
            if key is not None:
                changed.add(key)
            self.forget_subtree(node)
            node.remove()
        for index in range(first):
            key, spec, _allow_expand = desired[index]
            if self.update_row(existing[index], key, spec, tree):
                changed.add(key)
        for key, spec, allow_expand in desired[first:]:
            self.add_row(parent, tree, key, spec, allow_expand)
            changed.add(key)
        return changed

    def desired_plans(self, plans: list) -> list[tuple[tuple[str, int], RowSpec, bool]]:
        """Row specs for one panel's plans, in order."""
        return [
            (
                ("plan", plan.id),
                plan_spec(
                    plan,
                    self._progress,
                    attention=("plan", plan.id) in self._attention,
                ),
                bool(milestones),
            )
            for plan, milestones in plans
        ]

    def desired_milestones(self, plan_id: int) -> list[tuple[tuple[str, int], RowSpec, bool]]:
        """Row specs for one plan's visible milestones, in order."""
        out: list[tuple[tuple[str, int], RowSpec, bool]] = []
        for milestone, tasks in self._by_plan.get(plan_id, []):
            key = ("milestone", milestone.id)
            if key not in self._visible_keys:
                continue
            out.append(
                (
                    key,
                    milestone_spec(
                        milestone,
                        self.app.store,
                        self._progress,
                        attention=key in self._attention,
                    ),
                    bool(tasks),
                )
            )
        return out

    def desired_tasks(self, milestone_id: int) -> list[tuple[tuple[str, int], RowSpec, bool]]:
        """Row specs for one milestone's visible tasks, in order."""
        out: list[tuple[tuple[str, int], RowSpec, bool]] = []
        for task in self._tasks_by_milestone.get(milestone_id, []):
            key = ("task", task.id)
            if key not in self._visible_keys:
                continue
            out.append(
                (
                    key,
                    task_spec(
                        task,
                        self.app.store,
                        self._claims_map,
                        attention=key in self._attention,
                    ),
                    False,
                )
            )
        return out

    def reconcile_branches(self) -> set[tuple[str, int]]:
        """Reconcile the children of every branch that is already materialized."""
        changed: set[tuple[str, int]] = set()
        for tree in self.trees():
            for plan_node in list(tree.root.children):
                plan_key = self.node_key(plan_node)
                if plan_key is None or plan_key not in self._loaded:
                    continue
                changed |= self.reconcile_children(
                    plan_node, tree, self.desired_milestones(plan_key[1])
                )
                for milestone_node in list(plan_node.children):
                    milestone_key = self.node_key(milestone_node)
                    if milestone_key is None or milestone_key not in self._loaded:
                        continue
                    changed |= self.reconcile_children(
                        milestone_node, tree, self.desired_tasks(milestone_key[1])
                    )
        return changed
