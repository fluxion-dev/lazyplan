"""Modal update screen: download a verified wheel for the next launch."""

from __future__ import annotations

try:
    from textual import on
    from textual.app import ComposeResult
    from textual.binding import Binding
    from textual.containers import Horizontal, Vertical
    from textual.screen import ModalScreen
    from textual.widgets import Button, Label, Static

    _TEXTUAL_OK = True
except ImportError:  # pragma: no cover
    _TEXTUAL_OK = False

from ...design import escape_markup
from ...update_stage import stage_update
from ...upgrade import InstallInfo, UpgradeError, guard_message, parse_version

if _TEXTUAL_OK:

    class UpdateScreen(ModalScreen):
        """Show installed/latest and offer one staged download."""

        BINDINGS = [Binding("escape", "cancel", "Close", priority=True)]

        def __init__(self, installed: str, latest: str, info: InstallInfo) -> None:
            super().__init__()
            self.installed = installed
            self.latest = latest
            self.info = info
            self._done = False
            self._newer = self._is_newer()

        def _is_newer(self) -> bool:
            try:
                return parse_version(self.latest) > parse_version(self.installed)
            except UpgradeError:
                return False

        def compose(self) -> ComposeResult:
            with Vertical(id="dlg"):
                yield Label("Update lpui")
                yield Static(self._body(), id="update-body")
                with Horizontal(classes="btn-row"):
                    if self.info.upgradeable and self._newer:
                        yield Button(
                            f"Download v{self.latest}",
                            id="update-download",
                            variant="primary",
                        )
                    yield Button("Later", id="update-later")

        def _body(self) -> str:
            lines = [
                f"installed  v{escape_markup(self.installed)}",
                f"latest     v{escape_markup(self.latest)}",
                f"method     {escape_markup(self.info.method)}",
                "",
            ]
            if not self.info.upgradeable:
                lines.append(escape_markup(guard_message(self.info)))
            elif not self._newer:
                try:
                    same = parse_version(self.latest) == parse_version(self.installed)
                except UpgradeError:
                    same = False
                if same:
                    lines.append("You are already on the latest release.")
                else:
                    lines.append(
                        "Downgrades are disabled. This build is newer than the latest release."
                    )
            else:
                lines.append("Download now and it applies the next time lpui starts.")
            return "\n".join(lines)

        @on(Button.Pressed, "#update-download")
        def _download(self) -> None:
            if self._done or not self._newer or not self.info.upgradeable:
                return
            button = self.query_one("#update-download", Button)
            button.disabled = True
            button.label = "Downloading…"
            self.query_one("#update-body", Static).update("Downloading and verifying…")
            self.run_worker(self._download_worker, thread=True, exclusive=True)

        def _download_worker(self) -> None:
            try:
                staged = stage_update(self.latest, self.info.method, installed=self.installed)
            except Exception as exc:  # noqa: BLE001 - show the user the failure
                self.app.call_from_thread(self._failed, str(exc))
            else:
                self.app.call_from_thread(self._finished, staged.version)

        def _failed(self, detail: str) -> None:
            button = self.query_one("#update-download", Button)
            button.disabled = False
            button.label = "Retry download"
            self.query_one("#update-body", Static).update(
                f"[red]Download failed[/]\n\n{escape_markup(detail)}\n\nPress Retry or Esc."
            )

        def _finished(self, version: str) -> None:
            self._done = True
            self.query_one("#update-download", Button).display = False
            self.query_one("#update-later", Button).label = "Close"
            self.query_one("#update-body", Static).update(
                f"[green]Downloaded v{escape_markup(version)}[/]\n\n"
                "It will apply the next time lpui starts."
            )

        @on(Button.Pressed, "#update-later")
        def _later(self) -> None:
            self.dismiss(None)

        def action_cancel(self) -> None:
            self.dismiss(None)
