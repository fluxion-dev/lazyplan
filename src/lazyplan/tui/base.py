"""Shared declarations for the Textual app mixins."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from textual.app import App
from textual.widgets import Tree
from textual.widgets.tree import TreeNode

from ..messages import RowAction, SelectionChanged
from ..models import Milestone, Plan, Status, Task
from ..store import Store
from .state import AppState


class AppBase(App):
    """App attributes and cross-mixin declarations."""

    store: Store
    state: AppState
    _undo: list[dict] | None
    _row_nodes: dict[tuple[str, int], Any]
    _row_labels: dict[tuple[str, int], str]
    _last_click_key: tuple[str, int] | None
    _last_click_at: float
    _fp: Any
    _update_notice: str | None
    _update_latest: str
    _update_info: Any
    _startup_notice: str
    _toasted_version: str
    _update_timer: Any
    _update_checking: bool
    _git_cache: dict[str, tuple[float, dict[str, Any]]]
    _git_pending: set[str]
    _spinner_tick: int
    _spinner_rows: dict[tuple[str, int], str]
    _spinner_enabled: bool
    _spinner_timer: Any
    rev: Any

    @property
    def selected(self) -> tuple[str, int] | None:
        return self.state.selected

    @selected.setter
    def selected(self, value: tuple[str, int] | None) -> None:
        self.state.selected = value

    @property
    def status_filter(self) -> Status | None:
        return self.state.status_filter

    @status_filter.setter
    def status_filter(self, value: Status | None) -> None:
        self.state.status_filter = value

    @property
    def show_all(self) -> bool:
        return self.state.show_all

    @show_all.setter
    def show_all(self, value: bool) -> None:
        self.state.show_all = value

    @property
    def filter_text(self) -> str:
        return self.state.filter_text

    @filter_text.setter
    def filter_text(self, value: str) -> None:
        self.state.filter_text = value

    @property
    def source_filter(self) -> str:
        return self.state.source_filter

    @source_filter.setter
    def source_filter(self, value: str) -> None:
        self.state.source_filter = value

    @property
    def marked(self) -> set[tuple[str, int]]:
        return self.state.marked

    @marked.setter
    def marked(self, value: set[tuple[str, int]]) -> None:
        self.state.marked = value

    @property
    def _collapsed(self) -> set[tuple[str, int]]:
        return self.state.collapsed

    @_collapsed.setter
    def _collapsed(self, value: set[tuple[str, int]]) -> None:
        self.state.collapsed = value

    @property
    def _expanded(self) -> set[tuple[str, int]]:
        return self.state.expanded

    @_expanded.setter
    def _expanded(self, value: set[tuple[str, int]]) -> None:
        self.state.expanded = value

    @property
    def _pending_note(self) -> str:
        return self.state.pending_note

    @_pending_note.setter
    def _pending_note(self, value: str) -> None:
        self.state.pending_note = value

    @property
    def _mounted(self) -> bool:
        return self.state.mounted

    @_mounted.setter
    def _mounted(self, value: bool) -> None:
        self.state.mounted = value

    @property
    def _refreshing(self) -> bool:
        return self.state.refreshing

    @_refreshing.setter
    def _refreshing(self, value: bool) -> None:
        self.state.refreshing = value

    @property
    def _preview_key(self) -> tuple[str, int] | None:
        return self.state.preview_key

    @_preview_key.setter
    def _preview_key(self, value: tuple[str, int] | None) -> None:
        self.state.preview_key = value

    @property
    def _dirty_external(self) -> bool:
        return self.state.dirty_external

    @_dirty_external.setter
    def _dirty_external(self, value: bool) -> None:
        self.state.dirty_external = value

    @property
    def _narrow(self) -> bool | None:
        return self.state.narrow

    @_narrow.setter
    def _narrow(self, value: bool | None) -> None:
        self.state.narrow = value

    if TYPE_CHECKING:

        def _track(self, node: TreeNode) -> None:
            raise NotImplementedError

        def on_tree_node_highlighted(self, e: Tree.NodeHighlighted) -> None:
            raise NotImplementedError

        def _on_selection_changed(self, e: SelectionChanged) -> None:
            raise NotImplementedError

        def _preview_tasks(self, kind: str, full: dict[str, Any]) -> list[dict[str, Any]]:
            raise NotImplementedError

        def _preview_title(self, kind: str, oid: int, obj: dict[str, Any]) -> list[str]:
            raise NotImplementedError

        def _git_state(self, path: str) -> dict[str, Any]:
            raise NotImplementedError

        @staticmethod
        def _empty_git_state() -> dict[str, Any]:
            raise NotImplementedError

        def _load_git_state(self, path: str) -> None:
            raise NotImplementedError

        def _store_git_state(self, path: str, state: dict[str, Any]) -> None:
            raise NotImplementedError

        def _git_preview_bits(self, repos: list[dict[str, Any]]) -> list[str]:
            raise NotImplementedError

        def _preview_acceptance(self, lines: list[str], crits: list[dict]) -> None:
            raise NotImplementedError

        def _preview_source_summary(
            self, lines: list[str], links: list[dict], forge: list[dict], repos: list[dict]
        ) -> None:
            raise NotImplementedError

        def _preview_notes(self, lines: list[str], notes: list[dict[str, Any]]) -> None:
            raise NotImplementedError

        def _preview_common(self, lines: list[str], full: dict[str, Any]) -> None:
            raise NotImplementedError

        def _preview_plan(self, full: dict[str, Any], oid: int) -> list[str]:
            raise NotImplementedError

        def _preview_milestone(self, full: dict[str, Any], oid: int) -> list[str]:
            raise NotImplementedError

        def _preview_task(self, full: dict[str, Any], oid: int) -> list[str]:
            raise NotImplementedError

        def update_preview(self, force: bool = False) -> None:
            raise NotImplementedError

        def action_update_prompt(self) -> None:
            raise NotImplementedError

        def _on_row_action(self, e: RowAction) -> None:
            raise NotImplementedError

        @staticmethod
        def _node_key(node: TreeNode) -> tuple[str, int] | None:
            raise NotImplementedError

        def on_tree_node_collapsed(self, e: Tree.NodeCollapsed) -> None:
            raise NotImplementedError

        def on_tree_node_expanded(self, e: Tree.NodeExpanded) -> None:
            raise NotImplementedError

        def action_fold(self) -> None:
            raise NotImplementedError

        def action_fold_all(self) -> None:
            raise NotImplementedError

        def _poll(self) -> None:
            raise NotImplementedError

        def _source_stats(
            self, base: list[tuple[Plan, list[tuple[Milestone, list[Task]]]]]
        ) -> dict[tuple[str, int], tuple[int, int, int, int]]:
            raise NotImplementedError

        def _source_match(self, stats: tuple[int, int, int, int]) -> bool:
            raise NotImplementedError

        def _filter_tasks(
            self,
            base: list[tuple[Plan, list[tuple[Milestone, list[Task]]]]],
            keep: Callable[[Task], bool],
        ) -> list[tuple[Plan, list[tuple[Milestone, list[Task]]]]]:
            raise NotImplementedError

        def _filter_source_tree(
            self,
            base: list[tuple[Plan, list[tuple[Milestone, list[Task]]]]],
            stats: dict[tuple[str, int], tuple[int, int, int, int]],
        ) -> list[tuple[Plan, list[tuple[Milestone, list[Task]]]]]:
            raise NotImplementedError

        def _status_tree(
            self, base: list[tuple[Plan, list[tuple[Milestone, list[Task]]]]], status: Status | None
        ) -> list[tuple[Plan, list[tuple[Milestone, list[Task]]]]]:
            raise NotImplementedError

        def _filtered_tree(
            self, base: list[tuple[Plan, list[tuple[Milestone, list[Task]]]]] | None = None
        ) -> list[tuple[Plan, list[tuple[Milestone, list[Task]]]]]:
            raise NotImplementedError

        def action_clear_filter(self) -> None:
            raise NotImplementedError

        def _progress_map(
            self, base: list[tuple[Plan, list[tuple[Milestone, list[Task]]]]]
        ) -> dict[tuple[str, int], tuple[int, int]]:
            raise NotImplementedError

        def _status_text(self, counts: dict[str, int], note: str) -> str:
            raise NotImplementedError

        def _refresh_status(self, note: str = "") -> None:
            raise NotImplementedError

        def _paint_mark(self, key: tuple[str, int]) -> None:
            raise NotImplementedError

        def _row_width(self, tree: Tree, depth: int) -> int:
            raise NotImplementedError

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
            raise NotImplementedError

        def _apply_folds(self) -> None:
            raise NotImplementedError

        def _restore_selection(
            self, tree: Tree, prev_selected: tuple[str, int] | None, prev_cursor: Any
        ) -> None:
            raise NotImplementedError

        def refresh_all(self, note: str = "") -> None:
            raise NotImplementedError

        def action_refresh(self) -> None:
            raise NotImplementedError

        def _git_selection(self) -> tuple[str, int] | None:
            raise NotImplementedError

        def action_git_status(self) -> None:
            raise NotImplementedError

        def _git_status_worker(self, kind: str, oid: int) -> None:
            raise NotImplementedError

        def _git_status_done(self, entries: list[dict[str, Any]]) -> None:
            raise NotImplementedError

        def action_git_refresh(self) -> None:
            raise NotImplementedError

        def _git_refresh_worker(self, kind: str, oid: int) -> None:
            raise NotImplementedError

        def _git_refresh_done(self, result: dict[str, Any]) -> None:
            raise NotImplementedError

        def action_git_capture(self) -> None:
            raise NotImplementedError

        def action_open_pr(self) -> None:
            raise NotImplementedError

        def action_source_trail(self) -> None:
            raise NotImplementedError

        def _saved(self, note: str = "") -> None:
            raise NotImplementedError

        def action_filter_status(self) -> None:
            raise NotImplementedError

        def action_filter_source(self) -> None:
            raise NotImplementedError

        def action_toggle_show_all(self) -> None:
            raise NotImplementedError

        def action_help(self) -> None:
            raise NotImplementedError

        def _palette_context(self) -> dict[str, str | None]:
            raise NotImplementedError

        def action_command_palette(self) -> None:
            raise NotImplementedError

        def action_filter_text(self) -> None:
            raise NotImplementedError

        def _open_filter_prompt(self) -> None:
            raise NotImplementedError

        def action_toggle_mark(self) -> None:
            raise NotImplementedError

        def _marked_tasks(self) -> list[Task]:
            raise NotImplementedError

        def _bulk_capture(self, tasks: list[Task]) -> None:
            raise NotImplementedError

        def _bulk_status(self, status: Status) -> None:
            raise NotImplementedError

        def action_bulk_doing(self) -> None:
            raise NotImplementedError

        def action_bulk_done(self) -> None:
            raise NotImplementedError

        def action_bulk_block(self) -> None:
            raise NotImplementedError

        def action_bulk_release(self) -> None:
            raise NotImplementedError

        def action_undo_bulk(self) -> None:
            raise NotImplementedError

        def action_clear_marks(self) -> None:
            raise NotImplementedError

        def _selected_task(self) -> int | None:
            raise NotImplementedError

        def action_release_claim(self) -> None:
            raise NotImplementedError

        def action_force_release_claim(self) -> None:
            raise NotImplementedError

        def _release_claim(self, force: bool) -> None:
            raise NotImplementedError

        def _run_palette_command(self, command_id: str | None) -> None:
            raise NotImplementedError

        def _milestone_for_task_ctx(self) -> int | None:
            raise NotImplementedError

        def _plan_ctx(self) -> int | None:
            raise NotImplementedError

        def _cursor_is_root(self) -> bool:
            raise NotImplementedError

        def action_new_context(self) -> None:
            raise NotImplementedError

        def action_new_plan(self) -> None:
            raise NotImplementedError

        def action_new_milestone(self) -> None:
            raise NotImplementedError

        def action_new_task(self) -> None:
            raise NotImplementedError

        def action_toggle_status(self) -> None:
            raise NotImplementedError

        def action_move(self, status: Status) -> None:
            raise NotImplementedError

        def action_add_criterion(self) -> None:
            raise NotImplementedError

        def action_untick_criterion(self) -> None:
            raise NotImplementedError

        def action_edit_selection(self) -> None:
            raise NotImplementedError

        def action_criteria(self) -> None:
            raise NotImplementedError

        def action_delete(self) -> None:
            raise NotImplementedError

        def on_tree_node_selected(self, e: Tree.NodeSelected) -> None:
            raise NotImplementedError

        def note_click(self, key: tuple[str, int]) -> bool:
            raise NotImplementedError

        def _open_detail(self, kind: str, oid: int, edit: bool = False) -> None:
            raise NotImplementedError

        def action_export_md(self) -> None:
            raise NotImplementedError

        def action_open_detail(self) -> None:
            raise NotImplementedError

        def _remember_spinner(self, key: tuple[str, int], status: Status, label: str) -> None:
            raise NotImplementedError

        def _paint_spinner(self) -> None:
            raise NotImplementedError
