"""The plan tree widget: shared navigation plus double-click detail."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from textual import events
from textual.binding import Binding
from textual.widgets import Tree

from ...messages import RowAction, SelectionChanged
from ...tree_nav import NavTree
from ..controllers.tree import TreeController

if TYPE_CHECKING:
    from ..app import LazyplanApp


class FoldTree(NavTree):
    """Plan/milestone tree: j/k + arrows move, left/right fold, enter opens.

    Every mutation runs through the modal palette (c). Native Tree Space
    marks the selected row for bulk actions; shift+space stays parked.
    """

    BINDINGS = [
        Binding("enter", "open_detail", "Detail"),
        Binding("space", "toggle_mark", "Mark"),
    ]

    def on_tree_node_highlighted(self, e: Tree.NodeHighlighted) -> None:
        """Bubble selection as a custom message (guide/events pattern)."""
        key = TreeController.node_key(e.node)
        if key is not None:
            self.post_message(SelectionChanged(kind=key[0], oid=key[1]))

    def action_toggle_mark(self) -> None:
        """Space: mark or unmark the selected row."""
        cast("LazyplanApp", self.app).action_toggle_mark()

    def action_toggle_expand_all(self) -> None:
        """Shift+space: parked — use the modal palette for folding."""
        return

    def action_open_detail(self) -> None:
        """Enter: post intent; App handles via @on."""
        app = cast("LazyplanApp", self.app)
        if app.selected is not None:
            kind, oid = app.selected
            self.post_message(RowAction("open-detail", kind, oid))
        else:
            app.action_open_detail()

    async def _on_click(self, event: events.Click) -> None:
        """Single click selects; two quick clicks on one row open detail.

        Textual dispatches `_on_click` for every class in the MRO, so the
        base Tree handler still runs after this one. Do not call super()
        here or an arrow click would toggle twice and appear to do nothing.
        """
        app = cast("LazyplanApp", self.app)
        meta = event.style.meta
        if "line" not in meta or meta.get("toggle", False):
            return
        try:
            node = self.get_node_at_line(meta["line"])
        except IndexError:
            return
        if node is None:
            return
        key = TreeController.node_key(node)
        if key is None:
            return
        self.post_message(SelectionChanged(kind=key[0], oid=key[1]))
        if app.note_click(key):
            self.post_message(RowAction("open-detail", key[0], key[1]))
