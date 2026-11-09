"""Human review for agent proposals."""

from __future__ import annotations

import json
from typing import Any

try:
    from textual.app import ComposeResult
    from textual.binding import Binding
    from textual.containers import Horizontal, Vertical, VerticalScroll
    from textual.screen import Screen
    from textual.widgets import Button, OptionList, Static
    from textual.widgets.option_list import Option

    _TEXTUAL_OK = True
except ImportError:  # pragma: no cover
    _TEXTUAL_OK = False

from ....services import proposals as proposal_service
from ....store import Store
from ...shared.design import escape_markup


def _preview(row: dict[str, Any]) -> str:
    lines = [
        f"[bold]#{row['id']} {escape_markup(row['title'])}[/]",
        f"[dim]{escape_markup(row['kind'])} · {row['status']} · {escape_markup(row['actor'])}[/]",
    ]
    if row["summary"]:
        lines.append(escape_markup(row["summary"]))
    payload = json.dumps(row["payload"], indent=2, sort_keys=True, default=str)
    lines.append("\n" + escape_markup(payload[:6000]))
    return "\n".join(lines)


if _TEXTUAL_OK:

    class ProposalReviewScreen(Screen):
        """Apply or reject pending agent proposals."""

        BINDINGS = [
            Binding("escape", "back", "Back", priority=True),
            Binding("a", "apply", "Apply", priority=True),
            Binding("d", "reject", "Reject", priority=True),
        ]

        navigation_name = "proposals"

        def __init__(self, store: Store) -> None:
            super().__init__()
            self.store = store
            self._rows: dict[int, dict[str, Any]] = {}

        def compose(self) -> ComposeResult:
            with Vertical(id="proposal-page"):
                yield Static("", id="proposal-head")
                with Horizontal(id="proposal-main"):
                    yield OptionList(id="proposal-list")
                    with VerticalScroll(id="proposal-preview-scroll"):
                        yield Static("", id="proposal-preview")
                with Horizontal(id="proposal-actions", classes="btn-row"):
                    yield Button("Apply", id="proposal-apply", variant="primary")
                    yield Button("Reject", id="proposal-reject", variant="error")
                    yield Button("Close", id="proposal-close")

        def on_mount(self) -> None:
            self.query_one("#proposal-page").border_title = "PROPOSALS"
            self.reload()

        def reload(self) -> None:
            options = self.query_one("#proposal-list", OptionList)
            options.clear_options()
            rows = self.store.list_proposals("pending")
            self._rows = {row["id"]: row for row in rows}
            for row in rows:
                options.add_option(Option(f"#{row['id']} {row['title']}", id=str(row["id"])))
            self.query_one("#proposal-head", Static).update(
                f"[bold]{len(rows)} pending proposal{'s' if len(rows) != 1 else ''}[/]"
            )
            if rows:
                options.highlighted = 0
                self._show(rows[0])
            else:
                self.query_one("#proposal-preview", Static).update(
                    "No pending proposals. Ask the agent to propose a plan or edit."
                )

        def _show(self, row: dict[str, Any]) -> None:
            self.query_one("#proposal-preview", Static).update(_preview(row))

        def _selected(self) -> dict[str, Any] | None:
            option = self.query_one("#proposal-list", OptionList).highlighted_option
            if option is None or option.id is None:
                return None
            return self._rows.get(int(option.id))

        def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
            if event.option.id is None:
                return
            row = self._rows.get(int(event.option.id))
            if row is not None:
                self._show(row)

        def _apply(self) -> None:
            row = self._selected()
            if row is None:
                self.notify("select a proposal first")
                return
            try:
                proposal_service.apply_proposal(self.store, int(row["id"]), actor="human")
            except (KeyError, ValueError, RuntimeError) as exc:
                self.notify(f"error: {exc}")
                return
            self.notify(f"applied proposal #{row['id']}")
            refresh = getattr(self.app, "refresh_all", None)
            if callable(refresh):
                refresh("proposal applied")
            self.reload()

        def _reject(self) -> None:
            row = self._selected()
            if row is None:
                self.notify("select a proposal first")
                return
            try:
                proposal_service.reject_proposal(self.store, int(row["id"]), actor="human")
            except (KeyError, ValueError) as exc:
                self.notify(f"error: {exc}")
                return
            self.notify(f"rejected proposal #{row['id']}")
            self.reload()

        def action_apply(self) -> None:
            self._apply()

        def action_reject(self) -> None:
            self._reject()

        def action_back(self) -> None:
            self.app.pop_screen()

        def on_button_pressed(self, event: Button.Pressed) -> None:
            if event.button.id == "proposal-apply":
                self._apply()
            elif event.button.id == "proposal-reject":
                self._reject()
            elif event.button.id == "proposal-close":
                self.app.pop_screen()
