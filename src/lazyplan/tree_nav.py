"""Shared tree navigation for every tree view.

One set of gestures everywhere: j/k and up/down move, left/right fold or
unfold and walk to the parent/child, and clicking a row arrow toggles it.
Textual's Tree owns up/down, click-select, and arrow-click toggling; this
subclass adds the vim keys and left/right fold behavior.
"""

from __future__ import annotations

try:
    from textual.binding import Binding
    from textual.widgets import Tree

    _TEXTUAL_OK = True
except ImportError:  # pragma: no cover
    _TEXTUAL_OK = False


if _TEXTUAL_OK:

    class NavTree(Tree):
        """Tree with j/k movement and left/right fold-or-walk navigation."""

        BINDINGS = [
            Binding("j", "cursor_down", "Down", show=False),
            Binding("k", "cursor_up", "Up", show=False),
            Binding("left", "fold_left", "Fold", show=False),
            Binding("right", "fold_right", "Unfold", show=False),
        ]

        def action_fold_left(self) -> None:
            """Left: collapse an open node, else move to its parent."""
            node = self.cursor_node
            if node is None:
                return
            if node.allow_expand and node.is_expanded:
                node.collapse()
            elif node.parent is not None:
                self.move_cursor(node.parent)

        def action_fold_right(self) -> None:
            """Right: expand a closed node, else move to its first child."""
            node = self.cursor_node
            if node is None:
                return
            if node.allow_expand and not node.is_expanded:
                node.expand()
            elif node.children:
                self.move_cursor(node.children[0])
