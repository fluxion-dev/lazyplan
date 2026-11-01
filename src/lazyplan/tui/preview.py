"""Preview selection handling; rendering lives in views and widgets."""

from __future__ import annotations

try:
    from .query import query_one_opt
    from .widgets.git_panel import GitPanel
    from .widgets.preview_panel import PreviewPanel

    _TEXTUAL_OK = True
except ImportError:  # pragma: no cover
    _TEXTUAL_OK = False

from ..messages import RowAction, SelectionChanged
from .base import AppBase
from .views.git import build_git
from .views.preview import build_preview

if _TEXTUAL_OK:

    class PreviewMixin(AppBase):
        """Preview behavior."""

        def update_preview(self, force: bool = False) -> None:
            """Selection preview: a bounded summary, never the full plan."""
            panel = query_one_opt(self, "#preview", PreviewPanel)
            if panel is None:
                return
            if not force and self.selected == self._preview_key:
                return
            self._preview_key = self.selected
            git = query_one_opt(self, "#git", GitPanel)
            try:
                total_plans = self.store.counts()["plans"]
            except Exception:
                total_plans = 1
            if total_plans == 0:
                panel.show_empty("No plans yet", "press n to create one, or run: lpui plan add")
                if git is not None:
                    git.show_empty("No checkouts yet", "link a repo with: lpui repo add")
                return
            if self.selected is None:
                panel.show_empty("Nothing selected", "j/k or click a row — enter opens it")
                if git is not None:
                    git.show_empty("Nothing selected", "git context follows the selected row")
                return
            kind, oid = self.selected
            try:
                full = self.store.get_full(kind, oid)
            except Exception as exc:
                panel.show_error(f"could not load {kind} {oid}: {exc}")
                if git is not None:
                    git.show_error(f"could not load {kind} {oid}")
                return
            if full is None:
                panel.show_empty(f"{kind} {oid} is gone", "press r to refresh the tree")
                if git is not None:
                    git.show_empty("row is gone", "press r to refresh the tree")
                return
            repos = full.get("effective_repos") or full.get("repos") or []
            panel.show(build_preview(self.store, kind, oid, full, []))
            if git is not None:
                git.show(build_git(full, self.git_state_controller.snapshot(repos)))

        def update_git(self) -> None:
            """Refresh only the GIT pane when a checkout probe finishes."""
            git = query_one_opt(self, "#git", GitPanel)
            if git is None or self.selected is None:
                return
            kind, oid = self.selected
            try:
                full = self.store.get_full(kind, oid)
            except Exception:
                return
            if full is None:
                return
            repos = full.get("effective_repos") or full.get("repos") or []
            git.show(build_git(full, self.git_state_controller.snapshot(repos)))

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

        def _on_selection_changed(self, e: SelectionChanged) -> None:
            """Custom message (bubbles FoldTree -> App): track cursor."""
            self.selected = (e.kind, e.oid)
            self.update_preview()
