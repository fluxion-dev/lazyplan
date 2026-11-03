"""Modal export picker: choose a folder and filename for plan Markdown."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

try:
    from textual import on
    from textual.app import ComposeResult
    from textual.binding import Binding
    from textual.containers import Horizontal, Vertical, VerticalScroll
    from textual.screen import ModalScreen
    from textual.widgets import Button, DirectoryTree, Input, Label, Static

    _TEXTUAL_OK = True
except ImportError:  # pragma: no cover
    _TEXTUAL_OK = False

from .... import services
from ...shared.export import (
    ExportError,
    default_export_path,
    display_path,
    resolve_export_path,
    write_export,
)
from ...shared.render import render_plan_markdown
from .forms import ConfirmScreen

if TYPE_CHECKING:
    from ....store import Store


if _TEXTUAL_OK:

    class ExportScreen(ModalScreen[Path | None]):
        """Pick a destination for one plan's Markdown export."""

        BINDINGS = [Binding("escape", "cancel", "Cancel")]

        def __init__(
            self,
            store: Store,
            plan_id: int,
            plan_title: str = "",
            *,
            default_dir: Path | None = None,
        ) -> None:
            super().__init__()
            self.store = store
            self.plan_id = plan_id
            self.plan_title = plan_title
            self._default_dir = default_dir
            self._default_path = default_export_path(plan_id, default_dir=default_dir)

        def compose(self) -> ComposeResult:
            with Vertical(id="dlg", classes="export-dialog"):
                yield Label(
                    f"Export P{self.plan_id} · {self.plan_title}".rstrip(" ·"),
                    classes="form-title",
                    markup=False,
                )
                yield Label("Destination", classes="field-label")
                yield Input(value=display_path(self._default_path), id="export-path")
                yield Label("Folders", classes="field-label")
                with VerticalScroll(id="export-tree-scroll"):
                    yield DirectoryTree(self._default_path.parent, id="export-tree")
                yield Static("", id="export-error", markup=False)
                with Horizontal(classes="btn-row"):
                    yield Button("Export", id="export-ok", variant="primary")
                    yield Button("Cancel", id="export-cancel")

        def on_mount(self) -> None:
            self.query_one("#dlg").border_title = "EXPORT"
            width = self.app.size.width
            self.set_class(width < 80, "compact")
            self.set_class(width >= 120, "wide")
            self.query_one("#export-path", Input).focus()

        def _path_input(self) -> Input:
            return self.query_one("#export-path", Input)

        def _set_folder(self, folder: Path) -> None:
            """Point the destination at *folder* while keeping the filename."""
            current = Path(self._path_input().value)
            name = current.name or f"plan-P{self.plan_id}.md"
            self._path_input().value = display_path(folder / name)
            self._clear_error()

        def _clear_error(self) -> None:
            self.query_one("#export-error", Static).update("")

        def _show_error(self, message: str) -> None:
            self.query_one("#export-error", Static).update(message)
            self._path_input().focus()

        @on(DirectoryTree.DirectorySelected)
        def _folder_selected(self, event: DirectoryTree.DirectorySelected) -> None:
            event.stop()
            self._set_folder(event.path)

        @on(DirectoryTree.FileSelected)
        def _file_selected(self, event: DirectoryTree.FileSelected) -> None:
            event.stop()
            self._path_input().value = display_path(event.path)
            self._clear_error()

        @on(Button.Pressed, "#export-ok")
        def _export_pressed(self) -> None:
            self._attempt_export()

        @on(Button.Pressed, "#export-cancel")
        def _cancel_pressed(self) -> None:
            self.dismiss(None)

        @on(Input.Submitted, "#export-path")
        def _path_submitted(self) -> None:
            self._attempt_export()

        def _attempt_export(self) -> None:
            raw = self._path_input().value.strip()
            target = resolve_export_path(
                raw,
                self.plan_id,
                default_dir=self._default_dir,
            )
            entry = services.export_plan(self.store, self.plan_id)
            if entry is None:
                self._show_error(f"plan P{self.plan_id} no longer exists")
                return
            text = render_plan_markdown(entry) + "\n"
            if target.exists() and target.is_file():
                self._confirm_overwrite(target, text)
                return
            self._write(target, text)

        def _confirm_overwrite(self, target: Path, text: str) -> None:
            def cb(confirmed: bool | None) -> None:
                if confirmed:
                    self._write(target, text)
                else:
                    self._path_input().focus()

            self.app.push_screen(
                ConfirmScreen(
                    f"Overwrite {display_path(target)}?",
                    confirm_label="Overwrite",
                    variant="warning",
                ),
                cb,
            )

        def _write(self, target: Path, text: str) -> None:
            try:
                written = write_export(target, text, force=True)
            except ExportError as exc:
                self._show_error(str(exc))
                return
            self.dismiss(written)

        def action_cancel(self) -> None:
            self.dismiss(None)
