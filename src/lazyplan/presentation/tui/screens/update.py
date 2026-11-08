"""Modal update screen: download a verified wheel for the next launch."""

from __future__ import annotations

import os
import sys

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

from ....infrastructure.update_apply import build_apply_plan, spawn_windows_apply
from ....infrastructure.update_stage import StagedUpdate
from ....services.environment import (
    InstallInfo,
    UpgradeError,
    guard_message,
    parse_version,
    stage_update,
)
from ...shared.design import escape_markup
from ..navigation import NAV_BINDINGS, NavigationMixin

if _TEXTUAL_OK:

    class UpdateScreen(NavigationMixin, ModalScreen):
        """Show installed/latest and offer one staged download."""

        navigation_name = "update"

        BINDINGS = [*NAV_BINDINGS, Binding("escape", "cancel", "Close", priority=True)]

        def __init__(
            self,
            installed: str,
            latest: str,
            info: InstallInfo,
            *,
            windows: bool | None = None,
        ) -> None:
            super().__init__()
            self.installed = installed
            self.latest = latest
            self.info = info
            self._done = False
            self._windows = os.name == "nt" if windows is None else windows
            self._staged: StagedUpdate | None = None
            self._newer = self._is_newer()

        def _is_newer(self) -> bool:
            try:
                return parse_version(self.latest) > parse_version(self.installed)
            except UpgradeError:
                return False

        def on_mount(self) -> None:
            self.query_one("#dlg").border_title = "UPDATE"
            self.query_one("#update-restart", Button).display = False

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
                    yield Button("Restart now", id="update-restart", variant="primary")
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
            elif self._windows:
                lines.append("Download now, then restart to apply, or apply on the next launch.")
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
                self.app.call_from_thread(self._finished, staged)

        def _failed(self, detail: str) -> None:
            button = self.query_one("#update-download", Button)
            button.disabled = False
            button.label = "Retry download"
            self.query_one("#update-body", Static).update(
                f"[red]Download failed[/]\n\n{escape_markup(detail)}\n\nPress Retry or Esc."
            )

        def _finished(self, staged: StagedUpdate) -> None:
            self._done = True
            self._staged = staged
            self.query_one("#update-download", Button).display = False
            self.query_one("#update-later", Button).label = "Close"
            body = f"[green]Downloaded v{escape_markup(staged.version)}[/]\n\n"
            if self._windows:
                body += "Restart now to apply, or close and it applies on the next launch."
                self.query_one("#update-restart", Button).display = True
            else:
                body += "It will apply the next time lpui starts."
            self.query_one("#update-body", Static).update(body)

        @on(Button.Pressed, "#update-restart")
        def _restart(self) -> None:
            if self._staged is None:
                return
            try:
                plan = build_apply_plan(self._staged, exe=sys.executable, windows=True)
                spawn_windows_apply(plan, parent_pid=os.getpid())
            except Exception as exc:  # noqa: BLE001 - show the user the failure
                self.query_one("#update-body", Static).update(
                    f"[red]Could not start the update[/]\n\n{escape_markup(str(exc))}"
                )
                return
            self.app.exit()

        @on(Button.Pressed, "#update-later")
        def _later(self) -> None:
            self.dismiss(None)

        def action_cancel(self) -> None:
            self.dismiss(None)
