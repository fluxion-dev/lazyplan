"""Preview selection handling; rendering lives in views and widgets."""

from __future__ import annotations

try:
    from .query import query_one_opt
    from .widgets.agents_panel import AgentsPanel
    from .widgets.git_panel import GitPanel
    from .widgets.preview_panel import PreviewPanel

    _TEXTUAL_OK = True
except ImportError:  # pragma: no cover
    _TEXTUAL_OK = False

from ... import services
from ..shared.messages import RowAction, SelectionChanged
from .base import AppBase
from .views.control import build_control_strip
from .views.git import build_git
from .views.preview import PreviewBlock, PreviewDocument, build_preview

if _TEXTUAL_OK:

    class PreviewMixin(AppBase):
        """Preview behavior."""

        def update_agents(self) -> None:
            """Refresh the live claims in the agents pane."""
            panel = query_one_opt(self, "#agents", AgentsPanel)
            if panel is None:
                return
            panel.show(self.store)

        def update_preview(self, force: bool = False) -> None:
            """Selection preview: a bounded summary, never the full plan."""
            self.update_agents()
            panel = query_one_opt(self, "#preview", PreviewPanel)
            if panel is None:
                return
            if not force and self.selected == self._preview_key:
                return
            self._preview_key = self.selected
            git = query_one_opt(self, "#git", GitPanel)
            if self.selected is None:
                panel.show_empty("Nothing selected", "j/k or click a row — the overview follows it")
                if git is not None:
                    git.show_empty("Nothing selected", "git context follows the selected row")
                return
            kind, oid = self.selected
            if kind == "draft":
                self._show_draft_preview(oid)
                return
            try:
                total_plans = self.store.counts()["plans"]
            except Exception:
                total_plans = 1
            if total_plans == 0:
                panel.show_empty("No plans yet", "press n to create one, or run: lpui plan add")
                if git is not None:
                    git.show_empty("No checkouts yet", "link a repo with: lpui repo add")
                return
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
            panel.show(
                build_preview(kind, oid, full),
                strip=build_control_strip(self.store, kind, oid, full),
            )
            if git is not None:
                git.show(build_git(full, self.git_state_controller.snapshot(repos)))

        def _show_draft_preview(self, draft_id: int) -> None:
            """A draft summary in the overview while the draft screen is separate."""
            panel = query_one_opt(self, "#preview", PreviewPanel)
            if panel is None:
                return
            git = query_one_opt(self, "#git", GitPanel)
            try:
                detail = services.drafts.detail(self.store, draft_id)
            except (KeyError, ValueError) as exc:
                panel.show_error(f"could not load draft {draft_id}: {exc}")
                if git is not None:
                    git.show_empty("No git context", "drafts are not linked to checkouts")
                return
            draft = detail.draft
            blocks = [
                PreviewBlock("Why", (detail.document.why,)),
                PreviewBlock("What", (detail.document.what,)),
            ]
            if detail.annotations:
                lines = tuple(
                    f"A{row.id} [{row.status} {row.kind}] {row.block_key}: {row.body}"
                    for row in detail.annotations
                )
                blocks.append(PreviewBlock("Annotations", lines))
            panel.show(
                PreviewDocument(
                    header=f"D{draft.id} {draft.title}",
                    meta_line=(
                        f"{draft.status} · r{draft.revision}"
                        f" · {detail.open_annotations}/{detail.total_annotations} open"
                    ),
                    blocks=tuple(blocks),
                ),
            )
            if git is not None:
                git.show_empty("No git context", "drafts are not linked to checkouts")

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
            elif e.action == "fold-all":
                self.action_fold_all()
            e.stop()

        def _on_selection_changed(self, e: SelectionChanged) -> None:
            """Custom message (bubbles FoldTree -> App): track cursor."""
            self.selected = (e.kind, e.oid)
            self.update_preview()
