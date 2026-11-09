"""The plan tree widget: shared navigation and selection."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from textual import events
from textual.binding import Binding
from textual.widgets import Tree

from ...shared.messages import SelectionChanged
from ...shared.tree_nav import NavTree
from ..controllers.tree import TreeController

if TYPE_CHECKING:
    from ..app import LazyplanApp


class FoldTree(NavTree):
    """Plan/milestone tree: j/k + arrows move, left/right fold, click selects.

    Every mutation runs through the modal palette (c). Native Tree Space
    marks the selected row for bulk actions; shift+space stays parked.
    The root is a container only; plans render as the top-level rows.
    """

    show_root = False
    _reflow_width: int = 0

    BINDINGS = [
        Binding("space", "toggle_mark", "Mark"),
    ]

    def on_resize(self, event: events.Resize) -> None:
        """Reflow rows when the tree's own width changes."""
        if event.size.width == self._reflow_width:
            return
        self._reflow_width = event.size.width
        app = cast("LazyplanApp", self.app)
        if app._mounted:
            app.tree_controller.request_reflow()

    def on_tree_node_highlighted(self, e: Tree.NodeHighlighted) -> None:
        """Bubble selection as a custom message (guide/events pattern)."""
        key = TreeController.node_key(e.node)
        if key is not None:
            self.post_message(SelectionChanged(kind=key[0], oid=key[1]))

    def reflow(self) -> None:
        """Rebuild Textual's line and virtual-size caches after relabeling."""
        # set_label does not clear these caches, so a shrink would keep the
        # old virtual width and an unnecessary horizontal scrollbar.
        self._invalidate()

    def action_toggle_mark(self) -> None:
        """Space: mark or unmark the selected row."""
        cast("LazyplanApp", self.app).action_toggle_mark()

    def action_toggle_expand_all(self) -> None:
        """Shift+space: parked — use the modal palette for folding."""
        return

    async def _on_click(self, event: events.Click) -> None:
        """Single click selects the row; the overview follows it.

        Textual dispatches `_on_click` for every class in the MRO, so the
        base Tree handler still runs after this one. Do not call super()
        here or an arrow click would toggle twice and appear to do nothing.
        """
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
