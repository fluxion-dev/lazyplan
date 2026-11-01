"""Shared declarations for the Textual app mixins."""

from __future__ import annotations

from typing import Any

from textual.app import App
from textual.widgets.tree import TreeNode

from ..models import Status
from ..store import Store
from .controllers.git_state import GitStateController
from .controllers.metrics import MetricsController
from .controllers.spinner import SpinnerController
from .controllers.tree import TreeController
from .controllers.updates import UpdateController
from .state import AppState


class TuiHost:
    """The cross-mixin methods the shell calls on itself."""

    def refresh_all(self, note: str = "") -> None: ...
    def update_git(self) -> None: ...
    def _saved(self, note: str = "") -> None: ...
    def _paint_mark(self, key: tuple[str, int]) -> None: ...
    def _node_key(self, node: TreeNode) -> tuple[str, int] | None: ...
    def action_toggle_status(self) -> None: ...
    def _open_detail(self, kind: str, oid: int, edit: bool = False) -> None: ...
    def action_open_detail(self) -> None: ...
    def action_fold(self) -> None: ...
    def action_fold_all(self) -> None: ...
    def action_filter_text(self) -> None: ...
    def action_filter_status(self) -> None: ...
    def action_filter_source(self) -> None: ...
    def action_toggle_show_all(self) -> None: ...
    def action_toggle_mark(self) -> None: ...
    def action_clear_marks(self) -> None: ...
    def action_bulk_doing(self) -> None: ...
    def action_bulk_done(self) -> None: ...
    def action_bulk_block(self) -> None: ...
    def action_bulk_release(self) -> None: ...
    def action_undo_bulk(self) -> None: ...
    def action_update_prompt(self) -> None: ...


class AppBase(App, TuiHost):
    """App attributes and cross-mixin declarations."""

    store: Store
    state: AppState
    tree_controller: TreeController
    spinner_controller: SpinnerController
    git_state_controller: GitStateController
    update_controller: UpdateController
    metrics_controller: MetricsController
    _undo: list[dict] | None
    _row_nodes: dict[tuple[str, int], Any]
    _row_labels: dict[tuple[str, int], str]
    _last_click_key: tuple[str, int] | None
    _last_click_at: float
    _fp: Any
    _startup_notice: str
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

    @property
    def _update_notice(self) -> str | None:
        return self.update_controller.notice

    @_update_notice.setter
    def _update_notice(self, value: str | None) -> None:
        self.update_controller.notice = value

    @property
    def _update_latest(self) -> str:
        return self.update_controller.latest

    @_update_latest.setter
    def _update_latest(self, value: str) -> None:
        self.update_controller.latest = value

    @property
    def _update_info(self) -> Any:
        return self.update_controller.info

    @_update_info.setter
    def _update_info(self, value: Any) -> None:
        self.update_controller.info = value

    @property
    def _toasted_version(self) -> str:
        return self.update_controller.toasted_version

    @_toasted_version.setter
    def _toasted_version(self, value: str) -> None:
        self.update_controller.toasted_version = value

    @property
    def _update_timer(self) -> Any:
        return self.update_controller.timer

    @_update_timer.setter
    def _update_timer(self, value: Any) -> None:
        self.update_controller.timer = value

    @property
    def _update_checking(self) -> bool:
        return self.update_controller.checking

    @_update_checking.setter
    def _update_checking(self, value: bool) -> None:
        self.update_controller.checking = value

    @property
    def _spinner_tick(self) -> int:
        return self.spinner_controller.tick

    @_spinner_tick.setter
    def _spinner_tick(self, value: int) -> None:
        self.spinner_controller.tick = value

    @property
    def _spinner_rows(self) -> dict[tuple[str, int], str]:
        return self.spinner_controller.rows

    @_spinner_rows.setter
    def _spinner_rows(self, value: dict[tuple[str, int], str]) -> None:
        self.spinner_controller.rows = value

    @property
    def _spinner_enabled(self) -> bool:
        return self.spinner_controller.enabled

    @_spinner_enabled.setter
    def _spinner_enabled(self, value: bool) -> None:
        self.spinner_controller.enabled = value

    @property
    def _spinner_timer(self) -> Any:
        return self.spinner_controller.timer

    @_spinner_timer.setter
    def _spinner_timer(self, value: Any) -> None:
        self.spinner_controller.timer = value
