"""Lazy branch loading for the plan tree.

Split from ``tree.py`` so the controller stays inside the module budget. The
mixin owns materializing milestone and task nodes only when a branch opens.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.widgets import Tree
from textual.widgets.tree import TreeNode

from ....core.entities import Milestone, Task
from ...shared.design import apply_mark
from ..views.rows import milestone_spec, row_text, task_spec

if TYPE_CHECKING:
    from ..app import LazyplanApp


class LazyBranchMixin:
    """Load children on demand and restore only the branches that were open."""

    app: LazyplanApp
    _by_plan: dict[int, list[tuple[Milestone, list[Task]]]]
    _tasks_by_milestone: dict[int, list[Task]]
    _milestone_plan: dict[int, int]
    _task_milestone: dict[int, int]
    _loaded: set[tuple[str, int]]
    _model_keys: set[tuple[str, int]]
    _visible_keys: set[tuple[str, int]]
    _progress: dict[tuple[str, int], tuple[int, int]]
    _source_stats: dict[tuple[str, int], tuple[int, int, int, int]]
    _forge_map: dict
    _vcs_map: dict
    _claims_map: dict
    _loading: bool

    def has_model_children(self, key: tuple[str, int]) -> bool:
        """True when the model knows children for this plan or milestone."""
        if key[0] == "plan":
            return bool(self._by_plan.get(key[1]))
        if key[0] == "milestone":
            return bool(self._tasks_by_milestone.get(key[1]))
        return False

    def expand_all(self) -> None:
        """Load and open every branch in the current visible tree."""
        keys = [key for key in self._visible_keys if self.has_model_children(key)]
        keys.sort(key=lambda key: 0 if key[0] == "plan" else 1)
        for key in keys:
            self.ensure_path(key)
            node = self.app._row_nodes.get(key)
            if node is not None:
                self.load_branch(node, key)
                node.expand()
            self.app._expanded.add(key)
            self.app._collapsed.discard(key)

    def restore_expanded(self) -> None:
        """Load and open the branches that were open before this refresh."""
        for key in list(self.app._expanded):
            if key[0] not in ("plan", "milestone"):
                continue
            if key[0] == "milestone":
                self.ensure_path(key)
            node = self.app._row_nodes.get(key)
            if node is not None:
                self.load_branch(node, key)
                node.expand()

    def build_all_children(self) -> None:
        """Materialize filtered matches so search never hides a collapsed hit."""
        for plan in list(self._by_plan):
            plan_node = self.app._row_nodes.get(("plan", plan))
            if plan_node is not None:
                self.load_branch(plan_node, ("plan", plan))
        for milestone_id in list(self._tasks_by_milestone):
            milestone_node = self.app._row_nodes.get(("milestone", milestone_id))
            if milestone_node is not None:
                self.load_branch(milestone_node, ("milestone", milestone_id))

    def ensure_path(self, key: tuple[str, int]) -> None:
        """Load and open the ancestors needed for one row to exist."""
        if key not in self._model_keys:
            return
        kind, oid = key
        if kind == "plan":
            return
        if kind == "milestone":
            plan_id = self._milestone_plan.get(oid)
            if plan_id is None:
                return
            plan_key = ("plan", plan_id)
            plan_node = self.app._row_nodes.get(plan_key)
            if plan_node is None:
                return
            self.load_branch(plan_node, plan_key)
            plan_node.expand()
            self.app._expanded.add(plan_key)
            return
        milestone_id = self._task_milestone.get(oid)
        if milestone_id is None:
            return
        self.ensure_path(("milestone", milestone_id))
        milestone_node = self.app._row_nodes.get(("milestone", milestone_id))
        if milestone_node is not None:
            self.load_branch(milestone_node, ("milestone", milestone_id))
            milestone_node.expand()
            self.app._expanded.add(("milestone", milestone_id))

    def load_children(self, key: tuple[str, int]) -> None:
        """Public seam used by tests and the tree event handler."""
        node = self.app._row_nodes.get(key)
        if node is not None:
            self.load_branch(node, key)

    def load_branch(self, node: TreeNode, key: tuple[str, int]) -> None:
        """Create one branch's direct children exactly once."""
        if key in self._loaded or self._loading:
            return
        self._loaded.add(key)
        self._loading = True
        try:
            if key[0] == "plan":
                self._add_milestones(node, self._by_plan.get(key[1], []))
            elif key[0] == "milestone":
                self._add_tasks(node, self._tasks_by_milestone.get(key[1], []))
        finally:
            self._loading = False
            if self.app.spinner_controller.rows:
                self.app.spinner_controller.paint()

    def _add_milestones(
        self,
        plan_node: TreeNode,
        milestones: list[tuple[Milestone, list[Task]]],
    ) -> None:
        app = self.app
        for milestone, tasks in milestones:
            milestone_key = ("milestone", milestone.id)
            if milestone_key in app._row_nodes:
                continue
            spec = milestone_spec(milestone, app.store, self._progress, self._source_stats)
            app._row_specs[milestone_key] = spec
            text = self.app.tree_controller.render_row(
                milestone_key, spec, app.query_one("#tree", Tree)
            )
            milestone_node = plan_node.add(
                row_text(apply_mark(text, milestone_key in app.marked)),
                data={"kind": "milestone", "id": milestone.id},
                allow_expand=bool(tasks),
            )
            app._row_nodes[milestone_key] = milestone_node
            if milestone_key in app._expanded:
                self._add_tasks(milestone_node, tasks)
                milestone_node.expand()

    def _add_tasks(self, milestone_node: TreeNode, tasks: list[Task]) -> None:
        app = self.app
        data = milestone_node.data if isinstance(milestone_node.data, dict) else {}
        if "kind" in data and "id" in data:
            self._loaded.add((str(data["kind"]), int(data["id"])))
        for task in tasks:
            task_key = ("task", task.id)
            if task_key in app._row_nodes:
                continue
            spec = task_spec(task, app.store, self._forge_map, self._vcs_map, self._claims_map)
            app._row_specs[task_key] = spec
            text = self.app.tree_controller.render_row(task_key, spec, app.query_one("#tree", Tree))
            leaf = milestone_node.add_leaf(
                row_text(apply_mark(text, task_key in app.marked)),
                data={"kind": "task", "id": task.id},
            )
            app._row_nodes[task_key] = leaf


__all__ = ["LazyBranchMixin"]
