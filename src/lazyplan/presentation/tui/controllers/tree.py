"""Tree loading, filtering, folding, and selection restoration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from textual.widgets import Label, Static, Tree
from textual.widgets.tree import TreeNode

from .... import services
from ....core.entities import Milestone, Plan, Task
from ....core.policies.planning import progress_counts
from ....services.stats import attention_reasons
from ...shared.help import hint_bar
from ..views.rows import RowSpec
from .filtering import TreeFilter
from .lazy_branches import LazyBranchMixin
from .poll import PollMixin
from .reconcile import ReconcileMixin

if TYPE_CHECKING:
    from ..app import LazyplanApp
    from ..widgets.plan_tree import FoldTree


class TreeController(LazyBranchMixin, ReconcileMixin, PollMixin):
    """Owns the plan tree model and the row cache."""

    def __init__(self, app: LazyplanApp) -> None:
        self.app = app
        self.filters = TreeFilter(app)
        self.rebuilds = 0
        self._reflow_pending = False
        self._poll_worker: Any = None
        self._flush_timer: Any = None
        self._pending_structural = False
        self._pending_note = ""
        self._last_reap = 0.0
        self._by_plan: dict[int, list[tuple[Milestone, list[Task]]]] = {}
        self._tasks_by_milestone: dict[int, list[Task]] = {}
        self._milestone_plan: dict[int, int] = {}
        self._task_milestone: dict[int, int] = {}
        self._loaded: set[tuple[str, int]] = set()
        self._model_keys: set[tuple[str, int]] = set()
        self._visible_keys: set[tuple[str, int]] = set()
        self._progress: dict[tuple[str, int], tuple[int, int]] = {}
        self._source_stats: dict[tuple[str, int], tuple[int, int, int, int]] = {}
        self._forge_map: dict = {}
        self._vcs_map: dict = {}
        self._claims_map: dict = {}
        self._drift_map: dict = {}
        self._attention: set[tuple[str, int]] = set()
        self._loading = False

    @staticmethod
    def node_key(node: TreeNode) -> tuple[str, int] | None:
        data = getattr(node, "data", None)
        if isinstance(data, dict) and "kind" in data and "id" in data:
            return (str(data["kind"]), int(data["id"]))
        return None

    def trees(self) -> tuple[Tree, Tree]:
        """The active and finished tree widgets, in reading order."""
        return (
            self.app.query_one("#tree", Tree),
            self.app.query_one("#tree-finished", Tree),
        )

    def track(self, node: TreeNode) -> None:
        data = getattr(node, "data", None)
        if isinstance(data, dict) and "kind" in data and "id" in data:
            self.app.selected = (data["kind"], int(data["id"]))
            self.app.update_preview()
            self.app.metrics_controller.refresh()

    def apply_expansion(self, reveal: set[tuple[str, int]] | None = None) -> None:
        """Apply the expansion sets once, parents before children.

        This pass only reflects state; it never records a transition. Events
        posted by ``expand`` and ``collapse`` are ignored by the handlers
        because the node already agrees with the sets.
        """
        app = self.app
        effective = set(app._expanded)
        if reveal:
            effective.update(reveal)
        for kind in ("plan", "milestone"):
            for key in [key for key in app._row_nodes if key[0] == kind]:
                node = app._row_nodes.get(key)
                if node is None or not node.allow_expand:
                    continue
                if key in effective:
                    self.load_branch(node, key)
                    if not node.is_expanded:
                        node.expand()
                elif node.is_expanded:
                    node.collapse()

    def fold_all(self) -> None:
        """Collapse every loaded row, or load and open every branch."""
        expandable = [key for key in self._visible_keys if self.has_model_children(key)]
        loaded = [key for key, node in self.app._row_nodes.items() if node.allow_expand]
        if not loaded and not expandable:
            self.app.notify("nothing to fold")
            return
        if expandable and all(key in self.app._expanded for key in expandable):
            for key in loaded:
                self.app._row_nodes[key].collapse()
            self.app._expanded.clear()
            self.app._collapsed.update(loaded)
            return
        self.expand_all()

    def fold_one(self) -> None:
        """Toggle the selected plan or milestone (z)."""
        if self.app.selected is None:
            self.app.notify("select a row first (z folds it)")
            return
        key = self.app.selected
        if not self.has_model_children(key):
            self.app.notify("nothing to fold here")
            return
        if key not in self.app._row_nodes:
            self.materialize_path(key)
        node = self.app._row_nodes.get(key)
        if node is None:
            return
        if key in self.app._expanded:
            node.collapse()
            self.app._expanded.discard(key)
            self.app._collapsed.add(key)
            return
        self.load_branch(node, key)
        node.expand()
        self.app._expanded.add(key)
        self.app._collapsed.discard(key)

    @staticmethod
    def progress_map(
        base: list[tuple[Plan, list[tuple[Milestone, list[Task]]]]],
    ) -> dict[tuple[str, int], tuple[int, int]]:
        """Task progress per plan and milestone from one unfiltered snapshot."""
        out: dict[tuple[str, int], tuple[int, int]] = {}
        for plan, milestones in base:
            all_tasks = [task for _, tasks in milestones for task in tasks]
            out[("plan", plan.id)] = progress_counts(all_tasks)
            for milestone, tasks in milestones:
                out[("milestone", milestone.id)] = progress_counts(tasks)
        return out

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
        trees = self.trees()
        tree = trees[0]
        if not app._row_specs:
            return
        for key, spec in app._row_specs.items():
            self.render_row(key, spec, tree)
        app.spinner_controller.paint()
        for widget in trees:
            cast("FoldTree", widget).reflow()

    def show_empty(self, active_empty: bool, finished_empty: bool) -> None:
        """Swap each tree for its centered empty state when that panel is empty."""
        active_tree, finished_tree = self.trees()
        flipped = active_tree.display == active_empty or (finished_tree.display == finished_empty)
        active_tree.display = not active_empty
        finished_tree.display = not finished_empty
        self.app.query_one("#tree-empty", Static).display = active_empty
        self.app.query_one("#tree-finished-empty", Static).display = finished_empty
        if not flipped or len(self.app.screen_stack) > 1:
            return
        if not any(tree.has_focus for tree in (active_tree, finished_tree)):
            target = finished_tree if active_empty else active_tree
            if target.display:
                target.focus()

    def _attention_keys(
        self,
        base: list[tuple[Plan, list[tuple[Milestone, list[Task]]]]],
        reasons: dict[int, list[str]],
    ) -> set[tuple[str, int]]:
        """Task attention rolled up to milestones and plans."""
        keys: set[tuple[str, int]] = {
            ("task", task_id)
            for task_id, found in reasons.items()
            if any(reason != "blocked" for reason in found)
        }
        questions = self.app.store.questions_map()
        for plan, milestones in base:
            plan_hot = self._drift_map.get(plan.id, 0) > 0
            if any(question.status == "open" for question in questions.get(plan.id, [])):
                plan_hot = True
            for milestone, tasks in milestones:
                hot = any(task.id in reasons for task in tasks)
                if self._source_stats.get(("milestone", milestone.id), (0, 0, 0, 0))[2]:
                    hot = True
                if hot:
                    keys.add(("milestone", milestone.id))
                    plan_hot = True
            if self._source_stats.get(("plan", plan.id), (0, 0, 0, 0))[2]:
                plan_hot = True
            if plan_hot:
                keys.add(("plan", plan.id))
        for key, stats in self._source_stats.items():
            if stats[2]:
                keys.add(key)
        return keys

    def refresh_all(self, note: str = "") -> None:
        app = self.app
        self.rebuilds += 1
        active_tree, finished_tree = self.trees()
        app._refreshing = True
        try:
            prev_selected = app.selected
            view = self.capture_view()
            base = services.tree(app.store, status=None, archived="show", plan_mode="all")
            self._prepare_model(base)
            active, finished = self.filters.panels(base)
            visible = active + finished
            self._visible_keys = set()
            for plan, milestones in visible:
                self._visible_keys.add(("plan", plan.id))
                for milestone, tasks in milestones:
                    self._visible_keys.add(("milestone", milestone.id))
                    self._visible_keys.update(("task", task.id) for task in tasks)
            self._forge_map = app.store.forge_links_map()
            self._vcs_map = app.store.vcs_links_map()
            self._source_stats = self.filters.source_stats(
                visible, self._vcs_map, self._forge_map, app.store.repos_map()
            )
            self._claims_map = app.store.claims_map()
            self._drift_map = app.store.drift_counts()
            self._attention = self._attention_keys(base, attention_reasons(app.store))
            changed = self.reconcile_children(
                active_tree.root, active_tree, self.desired_plans(active)
            )
            changed |= self.reconcile_children(
                finished_tree.root, finished_tree, self.desired_plans(finished)
            )
            filtering = bool(app.filter_text.strip())
            if filtering:
                self.build_all_children()
            changed |= self.reconcile_branches()
            if not active_tree.root.is_expanded:
                active_tree.root.expand()
            if not finished_tree.root.is_expanded:
                finished_tree.root.expand()
            self.sync_filter_snapshot(filtering)
            self.apply_expansion(self.reveal_keys() if filtering else None)
            self.show_empty(not active, not finished)
            app.spinner_controller.paint()
            app.query_one("#hints", Label).update(
                hint_bar(max(10, app.size.width - 2), markup=True)
            )
            self.restore_view(view, prev_selected)
            app.metrics_controller.refresh()
            selected = app.selected
            force = selected != prev_selected or (selected is not None and selected in changed)
            app.update_preview(force=force)
        finally:
            app._refreshing = False

    def sync_filter_snapshot(self, filtering: bool) -> None:
        """Capture the baseline once per filter run and restore it when it clears."""
        app = self.app
        if filtering:
            if app.state.filter_snapshot is None:
                app.state.filter_snapshot = (set(app._expanded), set(app._collapsed))
            return
        snapshot = app.state.filter_snapshot
        if snapshot is None:
            return
        app._expanded.clear()
        app._expanded.update(snapshot[0])
        app._collapsed.clear()
        app._collapsed.update(snapshot[1])
        app.state.filter_snapshot = None

    def reveal_keys(self) -> set[tuple[str, int]]:
        """Branches the active filter may open without touching the baseline."""
        return {key for key in self._visible_keys if self.has_model_children(key)}

    def _prepare_model(self, base: list[tuple[Plan, list[tuple[Milestone, list[Task]]]]]) -> None:
        """Index the model once so expansion never re-reads the database."""
        self._by_plan = {plan.id: milestones for plan, milestones in base}
        self._tasks_by_milestone = {
            milestone.id: tasks for _, milestones in base for milestone, tasks in milestones
        }
        self._milestone_plan = {
            milestone.id: plan.id for plan, milestones in base for milestone, _tasks in milestones
        }
        self._task_milestone = {
            task.id: milestone.id
            for _, milestones in base
            for milestone, tasks in milestones
            for task in tasks
        }
        self._progress = self.progress_map(base)
        self._model_keys = set()
        for plan, milestones in base:
            self._model_keys.add(("plan", plan.id))
            for milestone, tasks in milestones:
                self._model_keys.add(("milestone", milestone.id))
                self._model_keys.update(("task", task.id) for task in tasks)

    def on_expanded(self, node: TreeNode) -> None:
        """Record a user expansion only; applied expansions already agree."""
        if self._loading or self.app.state.filter_snapshot is not None:
            return
        key = self.node_key(node)
        if key is None or key[0] not in ("plan", "milestone"):
            return
        if key in self.app._expanded:
            return
        self.app._expanded.add(key)
        self.app._collapsed.discard(key)
        self.load_branch(node, key)

    def on_collapsed(self, node: TreeNode) -> None:
        """Record a user collapse only; applied collapses already agree."""
        if self.app.state.filter_snapshot is not None:
            return
        key = self.node_key(node)
        if key is None or key[0] not in ("plan", "milestone"):
            return
        if key not in self.app._expanded:
            return
        self.app._expanded.discard(key)
        self.app._collapsed.add(key)

    def render_row(self, key: tuple[str, int], spec: RowSpec, tree: Tree) -> str:
        """Render and cache one row at the current tree width."""
        text = spec.markup(self.row_width(tree, spec.depth))
        self.app._row_labels[key] = text
        self.app.spinner_controller.remember(key, spec.status, text)
        return text
