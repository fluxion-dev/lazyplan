"""Selectable trust hubs: criteria, evidence, questions, and references."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

try:
    from textual import on
    from textual.app import ComposeResult
    from textual.binding import Binding
    from textual.containers import Horizontal, Vertical, VerticalScroll
    from textual.screen import Screen
    from textual.widgets import Label, OptionList, Static
    from textual.widgets.option_list import Option

    from ..navigation import NAV_BINDINGS, NavigationMixin

    _TEXTUAL_OK = True
except ImportError:  # pragma: no cover - stdlib-only interpreter
    _TEXTUAL_OK = False

from ...shared import registry


@dataclass(frozen=True)
class HubEntry:
    """One selectable hub row and its preview body."""

    oid: int
    label: str
    body: str
    kind: str = ""
    ref: str = ""


def plan_id_for(store: Any, kind: str, oid: int) -> int | None:
    """Owning plan for a plan, milestone, or task."""
    if kind == "plan":
        return oid
    if kind == "milestone":
        milestone = store.get_milestone(oid)
        return milestone.plan_id if milestone else None
    task = store.get_task(oid)
    if task is None:
        return None
    milestone = store.get_milestone(task.milestone_id)
    return milestone.plan_id if milestone else None


if _TEXTUAL_OK:

    class HubScreen(NavigationMixin, Screen):
        """List of entities on the left, preview on the right, actions on keys."""

        navigation_name = "hub"
        kind = ""
        title = "hub"
        empty = "Nothing here yet."

        BINDINGS = [
            *NAV_BINDINGS,
            Binding("escape", "back", "Back", priority=True),
            Binding("a", "add", "Add"),
            Binding("x", "hub_toggle", "Toggle"),
            Binding("p", "prove", "Prove"),
            Binding("d", "delete", "Delete"),
            Binding("D", "force", "Force"),
            Binding("n", "note", "Note"),
            Binding("u", "filter", "Filter"),
            Binding("l", "relate", "Relate"),
            Binding("L", "unrelate", "Unrelate"),
            Binding("o", "open_value", "Open"),
            Binding("r", "refresh", "Refresh"),
        ]

        def __init__(self, store: Any) -> None:
            super().__init__()
            self.store = store
            self.entries: list[HubEntry] = []

        def compose(self) -> ComposeResult:
            with Vertical(id="hub-page"):
                yield Static("", id="hub-head")
                with Horizontal(id="hub-main"):
                    with VerticalScroll(id="hub-list-wrap"):
                        yield OptionList(id="hub-list")
                    with VerticalScroll(id="hub-preview"):
                        yield Static("", id="hub-preview-body")
                yield Label("", id="hub-hints")

        def on_mount(self) -> None:
            width = self.app.size.width
            self.set_class(width < 80, "compact")
            self.set_class(width >= 120, "wide")
            self.query_one("#hub-page").border_title = f" {self.title} "
            self.query_one("#hub-list-wrap").border_title = " list "
            self.query_one("#hub-preview").border_title = " detail "
            self._reload()
            self.query_one("#hub-list", OptionList).focus()

        def _reload(self) -> None:
            entries = self.load_entries()
            self.entries = entries
            head = f"{registry_action_count(self.kind)} actions · {len(entries)} rows"
            if not entries:
                head = f"{self.empty} · {len(entries)} rows"
            self.query_one("#hub-head", Static).update(head)
            options = self.query_one("#hub-list", OptionList)
            options.clear_options()
            for index, entry in enumerate(entries):
                options.add_option(Option(entry.label, id=str(index)))
            if entries:
                options.highlighted = 0
            self._preview(0 if entries else None)
            self.query_one("#hub-hints", Label).update(self._hints())
            self.query_one("#hub-page").border_title = f" {self.title} "

        def _hints(self) -> str:
            labels = [label for _aid, label in registry.hub_actions(self.kind)]
            return " · ".join(f"{label.lower()}" for label in labels)

        def _preview(self, index: int | None) -> None:
            body = (
                self.entries[index].body
                if index is not None and index < len(self.entries)
                else self.empty
            )
            self.query_one("#hub-preview-body", Static).update(body)

        def _selected(self) -> HubEntry | None:
            highlighted = self.query_one("#hub-list", OptionList).highlighted
            if highlighted is None or highlighted >= len(self.entries):
                return None
            return self.entries[highlighted]

        def _notify_empty(self) -> None:
            self.notify(self.empty, timeout=3)

        # Hooks overridden by the four hubs.
        def load_entries(self) -> list[HubEntry]:
            return []

        def add(self) -> None:
            self._notify_empty()

        def toggle(self) -> None:
            self._notify_empty()

        def prove(self) -> None:
            self._notify_empty()

        def delete_row(self) -> None:
            self._notify_empty()

        def force(self) -> None:
            self._notify_empty()

        def note(self) -> None:
            self._notify_empty()

        def filter_toggle(self) -> None:
            self._notify_empty()

        def relate(self) -> None:
            self._notify_empty()

        def unrelate(self) -> None:
            self._notify_empty()

        def open_entry(self, entry: HubEntry) -> None:
            self.notify("this hub has no child view", timeout=3)

        def open_value(self) -> None:
            self.notify("nothing to open", timeout=3)

        @on(OptionList.OptionHighlighted, "#hub-list")
        def _highlight(self, event: OptionList.OptionHighlighted) -> None:
            self._preview(self.query_one("#hub-list", OptionList).highlighted)

        @on(OptionList.OptionSelected, "#hub-list")
        def _select(self, event: OptionList.OptionSelected) -> None:
            entry = self._selected()
            if entry is not None:
                self.open_entry(entry)
            event.stop()

        def action_add(self) -> None:
            self.add()

        def action_hub_toggle(self) -> None:
            self.toggle()

        def action_prove(self) -> None:
            self.prove()

        def action_delete(self) -> None:
            self.delete_row()

        def action_force(self) -> None:
            self.force()

        def action_note(self) -> None:
            self.note()

        def action_filter(self) -> None:
            self.filter_toggle()

        def action_relate(self) -> None:
            self.relate()

        def action_unrelate(self) -> None:
            self.unrelate()

        def action_open_value(self) -> None:
            self.open_value()

        def action_refresh(self) -> None:
            self._reload()

        def action_back(self) -> None:
            handler = getattr(self.app, "action_history_back", None)
            if callable(handler):
                handler()
            else:
                self.app.pop_screen()


def registry_action_count(kind: str) -> int:
    """Number of canonical actions a hub exposes."""
    return len(registry.hub_actions(kind))
