"""Tree loading, filtering, folding, and selection restoration."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, cast

from textual.widgets import Label, Static, Tree
from textual.widgets.tree import TreeNode

from .... import services
from ....core.entities import Milestone, Plan, Task
from ....core.policies.planning import progress_counts
from ....services.stats import attention_reasons
from ...shared.help import hint_bar
from ..views.rows import RowSpec, milestone_spec, plan_spec, row_text, task_spec
from .filtering import TreeFilter
from .lazy_branches import LazyBranchMixin

REAP_INTERVAL = 300.0
COALESCE_SECONDS = 0.25

if TYPE_CHECKING:
    from ..app import LazyplanApp
    from ..widgets.plan_tree import FoldTree


class TreeController(LazyBranchMixin):
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

    def apply_folds(self) -> None:
        """Reflect saved expansion on the rows that exist; never load here."""
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
            self.ensure_path(key)
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

    def poll(self) -> None:
        """Start one background read of the poll keys, if none is pending."""
        if self._apply_dirty():
            return
        if self._poll_worker is not None and not self._poll_worker.is_finished:
            return
        self._poll_worker = self.app.run_worker(
            self._poll_in_worker,
            name="poll",
            group="poll",
            thread=True,
            exit_on_error=False,
        )

    def poll_now(self) -> None:
        """Read and apply one poll on the calling thread; tests use this."""
        if self._apply_dirty():
            return
        state = self._read_state()
        if state is not None:
            self._apply_poll(*state)

    def _poll_in_worker(self) -> None:
        state = self._read_state()
        if state is None:
            return
        try:
            self.app.call_from_thread(self._apply_poll, *state)
        except Exception:
            pass

    def _read_state(self) -> tuple | None:
        """Read both poll keys and the newest event; never touches widgets."""
        app = self.app
        now = time.time()
        if now - self._last_reap >= REAP_INTERVAL:
            self._last_reap = now
            try:
                app.store.reap_idle_sessions(now=now)
            except Exception:
                pass
        try:
            structural = app.store.fingerprint()
            live = app.store.live_fingerprint()
        except Exception:
            return None
        events = app.store.feed(1) if structural != app._fp else []
        return (structural, live, events)

    def _apply_dirty(self) -> bool:
        """Apply a change deferred by a modal once that modal closes."""
        app = self.app
        if not app._dirty_external or len(app.screen_stack) > 1:
            return False
        app._dirty_external = False
        self._pending_structural = False
        app.rev += 1
        return True

    def _apply_poll(self, fingerprint: tuple, live: tuple, events: list[dict]) -> None:
        """Compare one worker result and schedule the cheapest refresh."""
        app = self.app
        structural_changed = fingerprint != app._fp
        live_changed = live != app._live_fp
        if not structural_changed and not live_changed:
            return
        app._fp = fingerprint
        app._live_fp = live
        if live_changed:
            app.update_agents()
        if not structural_changed:
            return
        note = "db changed — refreshed"
        if events:
            event = events[0]
            event_id = int(event.get("id") or 0)
            if event_id > app._last_event_id:
                app._last_event_id = event_id
                note = f"[{event['actor']}] {event['kind']}/{event['action']}: {event['detail']}"
                try:
                    app.notify(note, timeout=4)
                except Exception:
                    pass
        self._pending_note = note
        self._pending_structural = True
        self._schedule_flush()

    def _schedule_flush(self) -> None:
        """Coalesce a burst of structural writes behind one short timer."""
        if self._flush_timer is not None:
            return
        self._flush_timer = self.app.set_timer(COALESCE_SECONDS, self._flush_soon)

    def _flush_soon(self) -> None:
        self._flush_timer = None
        self._flush_structural()

    def _flush_structural(self) -> None:
        """Rebuild the tree once for every change in the coalescing window."""
        if not self._pending_structural:
            return
        app = self.app
        if len(app.screen_stack) > 1:
            app._dirty_external = True
            return
        self._pending_structural = False
        app._pending_note = self._pending_note
        app.rev += 1

    def capture_view(self) -> dict[str, Any]:
        """Remember the cursor row, focus, and each tree's scroll offset."""
        view: dict[str, Any] = {"cursor": None, "focus": None, "scroll": {}}
        for tree in self.trees():
            view["scroll"][tree.id] = (tree.scroll_x, tree.scroll_y)
            if tree.has_focus:
                view["focus"] = tree.id
                cursor = tree.cursor_node
                view["cursor"] = self.node_key(cursor) if cursor is not None else None
        return view

    def restore_view(self, view: dict[str, Any], prev_selected: tuple[str, int] | None) -> None:
        """Restore cursor, scroll, and focus after an in-place refresh."""
        app = self.app
        target = view.get("cursor")
        if target not in app._row_nodes:
            target = prev_selected if prev_selected in app._row_nodes else None
        if target is None:
            target = self.fallback_key()
        if target is None:
            return
        if app.selected not in app._row_nodes:
            app.selected = target
        try:
            app.call_after_refresh(lambda: self._place_view(view, target))
        except Exception:
            pass

    def fallback_key(self) -> tuple[str, int] | None:
        """First visible plan row, else the first row of any kind."""
        for key, node in self.app._row_nodes.items():
            if key[0] == "plan" and node.tree.display:
                return key
        return next(iter(self.app._row_nodes), None)

    def _place_view(self, view: dict[str, Any], target: tuple[str, int]) -> None:
        """Apply the saved offsets, then scroll only if the cursor is off-screen."""
        app = self.app
        node = app._row_nodes.get(target)
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
        app.spinner_controller.rows = {}
        for key, spec in app._row_specs.items():
            self.render_row(key, spec, tree)
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
        prev_selected = app.selected
        view = self.capture_view()
        prev_cursor = view["cursor"]
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
        changed = self.reconcile_children(active_tree.root, active_tree, self.desired_plans(active))
        changed |= self.reconcile_children(
            finished_tree.root, finished_tree, self.desired_plans(finished)
        )
        if app.filter_text.strip():
            self.build_all_children()
        changed |= self.reconcile_branches()
        active_tree.root.expand()
        finished_tree.root.expand()
        app._collapsed &= self._model_keys
        app._expanded &= self._model_keys
        self.restore_expanded()
        for candidate in (prev_selected, prev_cursor):
            if candidate in self._model_keys:
                self.ensure_path(candidate)
        self.apply_folds()
        self.show_empty(not active, not finished)
        app.spinner_controller.paint()
        app.query_one("#hints", Label).update(hint_bar(max(10, app.size.width - 2), markup=True))
        self.restore_view(view, prev_selected)
        app.metrics_controller.refresh()
        selected = app.selected
        force = selected != prev_selected or (selected is not None and selected in changed)
        app.update_preview(force=force)

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
        if self.app._refreshing or self._loading:
            return
        key = self.node_key(node)
        if key is not None:
            self.app._collapsed.discard(key)
            if key[0] in ("plan", "milestone"):
                self.app._expanded.add(key)
                self.load_branch(node, key)

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
        app = self.app
        existing = list(parent.children)
        existing_keys = [self.node_key(node) for node in existing]
        wanted = [item[0] for item in desired]
        first = min(len(existing_keys), len(wanted))
        for index in range(first):
            if existing_keys[index] != wanted[index]:
                first = index
                break
        changed: set[tuple[str, int]] = set()
        recreated: set[tuple[str, int]] = set()
        for node in existing[first:]:
            key = self.node_key(node)
            if key is not None:
                if key in self._loaded:
                    recreated.add(key)
                changed.add(key)
            self.forget_subtree(node)
            node.remove()
        for index in range(first):
            key, spec, _allow_expand = desired[index]
            if self.update_row(existing[index], key, spec, tree):
                changed.add(key)
        for key, spec, allow_expand in desired[first:]:
            node = self.add_row(parent, tree, key, spec, allow_expand)
            changed.add(key)
            if key in recreated or key in app._expanded:
                self.load_branch(node, key)
                if key in app._expanded:
                    node.expand()
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
