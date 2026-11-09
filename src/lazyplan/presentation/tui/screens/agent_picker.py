"""Pick one configured ACP agent."""

from __future__ import annotations

from ....infrastructure.agents import AgentProfile, load_catalog

try:
    from textual.app import ComposeResult
    from textual.binding import Binding
    from textual.containers import Vertical
    from textual.screen import ModalScreen
    from textual.widgets import OptionList, Static
    from textual.widgets.option_list import Option

    _TEXTUAL_OK = True
except ImportError:  # pragma: no cover
    _TEXTUAL_OK = False


if _TEXTUAL_OK:

    class AgentPickerScreen(ModalScreen[AgentProfile | None]):
        """Select the agent command for the next workbench run."""

        BINDINGS = [Binding("escape", "cancel", "Cancel", priority=True)]

        def __init__(self) -> None:
            super().__init__()
            self._profiles: dict[str, AgentProfile] = {}
            self._default = ""

        def compose(self) -> ComposeResult:
            with Vertical(id="agent-picker"):
                yield Static("", id="agent-picker-head")
                yield OptionList(id="agent-picker-list")

        def on_mount(self) -> None:
            self.query_one("#agent-picker").border_title = "AGENT"
            try:
                profiles, default = load_catalog()
            except ValueError as exc:
                self.query_one("#agent-picker-head", Static).update(f"error: {exc}")
                return
            self._default = default
            options = self.query_one("#agent-picker-list", OptionList)
            for profile in profiles:
                self._profiles[profile.key] = profile
                marker = "* " if profile.key == default else "  "
                options.add_option(
                    Option(f"{marker}{profile.title} · {profile.key}", id=profile.key)
                )
            self.query_one("#agent-picker-head", Static).update(
                "[bold]Choose an ACP agent[/]\n[dim]The default is marked with *[/]"
            )
            if profiles:
                options.highlighted = 0

        def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
            if event.option.id is not None:
                self.dismiss(self._profiles.get(event.option.id))

        def action_cancel(self) -> None:
            self.dismiss(None)
