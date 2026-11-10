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


if _TEXTUAL_OK:

    class HubScreen(NavigationMixin, Screen):
        """List of entities on the left, preview on the right, actions on keys."""

        navigation_name = "hub"
        kind = ""
        title = "hub"
        empty = "Nothing here yet."
        primary_hint: tuple[str, str] | None = None

        BINDINGS = [
            *NAV_BINDINGS,
            Binding("escape", "back", "Back", priority=True),
            Binding("a", "add", "Add"),
            Binding("p", "prove", "Prove"),
            Binding("d", "delete", "Delete"),
            Binding("D", "force", "Force"),
            Binding("n", "note", "Note"),
            Binding("l", "relate", "Relate"),
            Binding("L", "unrelate", "Unrelate"),
            Binding("o", "open_value", "Open"),
            Binding("g", "source_hub", "Source"),
            Binding("r", "refresh", "Refresh"),
        ]

        def __init__(self, store: Any) -> None:
            super().__init__()
            self.store = store
            self.entries: list[HubEntry] = []

        @property
        def source_parent(self) -> tuple[str, int] | None:
            """Row whose source trail this hub can open with `g`."""
            return None

        def compose(self) -> ComposeResult:
            with Vertical(id="hub-page"):
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
            self.query_one("#hub-preview").border_title = " overview "
            self._reload()
            self.query_one("#hub-list", OptionList).focus()

        def _reload(self) -> None:
            entries = self.load_entries()
            self.entries = entries
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
            """Primary action first, then the remaining keyed actions."""
            parts: list[str] = []
            primary_key = ""
            if self.primary_hint is not None:
                primary_key, primary_label = self.primary_hint
                parts.append(f"[reverse] {primary_key} [/]{primary_label}")
            for action_id, label in registry.hub_actions(self.kind):
                action = registry.by_id(action_id)
                key = action.key if action is not None else ""
                if not key or key == primary_key:
                    continue
                parts.append(f"[dim]{key}[/] {label.lower()}")
            return " · ".join(parts) if parts else "esc back"

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

        def action_source_hub(self) -> None:
            """Open the source trail for this hub's parent row."""
            parent = self.source_parent
            if parent is None:
                self.notify("this hub has no source trail", timeout=3)
                return
            opener = getattr(self.app, "open_source", None)
            if callable(opener):
                opener(parent[0], parent[1])
                return
            from .source import SourceScreen

            self.app.push_screen(SourceScreen(self.store, parent[0], parent[1]))

        def action_back(self) -> None:
            handler = getattr(self.app, "action_history_back", None)
            if callable(handler):
                handler()
            else:
                self.app.pop_screen()
