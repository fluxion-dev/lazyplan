"""Preview selection handling; rendering lives in views and widgets."""

from __future__ import annotations

try:
    from .query import query_one_opt
    from .widgets.preview_panel import PreviewPanel

    _TEXTUAL_OK = True
except ImportError:  # pragma: no cover
    _TEXTUAL_OK = False

from ..design import EMPTY_NO_PLANS
from ..messages import RowAction, SelectionChanged
from .base import AppBase
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
            try:
                total_plans = self.store.counts()["plans"]
            except Exception:
                total_plans = 1
            if total_plans == 0:
                panel.show_text(EMPTY_NO_PLANS)
                return
            if self.selected is None:
                panel.show_text("select a plan (j/k or click) — enter opens it")
                return
            kind, oid = self.selected
            try:
                full = self.store.get_full(kind, oid)
            except Exception:
                panel.show_text(f"{kind} {oid} — gone, press r")
                return
            if full is None:
                panel.show_text(f"{kind} {oid} — gone, press r")
                return
            repos = full.get("effective_repos") or full.get("repos") or []
            git_bits = self.git_state_controller.preview_bits(repos)
            panel.show(build_preview(self.store, kind, oid, full, git_bits))

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
