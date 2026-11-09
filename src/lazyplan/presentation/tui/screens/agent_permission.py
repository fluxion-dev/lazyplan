"""Permission modal for one ACP tool request."""

from __future__ import annotations

from typing import Literal

try:
    from textual.app import ComposeResult
    from textual.binding import Binding
    from textual.containers import Horizontal, Vertical, VerticalScroll
    from textual.screen import ModalScreen
    from textual.widgets import Button, Static

    _TEXTUAL_OK = True
except ImportError:  # pragma: no cover
    _TEXTUAL_OK = False

from ....infrastructure.agents import PermissionOption, PermissionRequest
from ...shared.design import escape_markup


def _details(permission: PermissionRequest) -> str:
    tool = permission.tool
    lines = [
        f"[bold]{escape_markup(tool.title or tool.name or 'agent tool')}[/]",
        f"[dim]{escape_markup(tool.kind)} · {escape_markup(tool.status)}[/]",
    ]
    for item in tool.content:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "diff":
            lines.append(f"\n[bold]{escape_markup(str(item.get('path') or 'file'))}[/]")
            old = str(item.get("oldText") or "")
            new = str(item.get("newText") or "")
            if old:
                lines.append("[dim]old[/]\n" + escape_markup(old[:2000]))
            if new:
                lines.append("[dim]new[/]\n" + escape_markup(new[:2000]))
        elif item.get("type") == "content":
            inner = item.get("content")
            if isinstance(inner, dict) and inner.get("type") == "text":
                lines.append(escape_markup(str(inner.get("text") or "")))
    return "\n".join(lines)


if _TEXTUAL_OK:

    class AgentPermissionScreen(ModalScreen[str | None]):
        """Allow once, allow always, or reject one tool call."""

        BINDINGS = [Binding("escape", "reject", "Reject", priority=True)]

        def __init__(self, permission: PermissionRequest) -> None:
            super().__init__()
            self.permission = permission

        def compose(self) -> ComposeResult:
            with Vertical(id="agent-permission"):
                with VerticalScroll(id="agent-permission-scroll"):
                    yield Static(_details(self.permission), id="agent-permission-body")
                with Horizontal(classes="btn-row"):
                    for index, option in enumerate(self.permission.options):
                        yield Button(
                            _label(option),
                            id=f"perm-{index}",
                            variant=_variant(option),
                        )
                    yield Button("Reject", id="perm-cancel", variant="error")

        def on_mount(self) -> None:
            self.query_one("#agent-permission").border_title = "PERMISSION"

        def on_button_pressed(self, event: Button.Pressed) -> None:
            if event.button.id == "perm-cancel":
                self.dismiss(None)
                return
            if event.button.id is None or not event.button.id.startswith("perm-"):
                return
            index = int(event.button.id.removeprefix("perm-"))
            if 0 <= index < len(self.permission.options):
                self.dismiss(self.permission.options[index].option_id)

        def action_reject(self) -> None:
            self.dismiss(None)


def _label(option: PermissionOption) -> str:
    return option.name or option.option_id


def _variant(
    option: PermissionOption,
) -> Literal["default", "primary", "success", "warning", "error"]:
    if option.kind.startswith("reject"):
        return "error"
    if option.kind == "allow_always":
        return "warning"
    return "primary"
