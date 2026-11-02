"""Tree event handlers and thin delegations to the tree controller."""

from __future__ import annotations

try:
    from textual.widgets import Tree
    from textual.widgets.tree import TreeNode

    _TEXTUAL_OK = True
except ImportError:  # pragma: no cover
    _TEXTUAL_OK = False

from .base import AppBase
from .controllers.tree import TreeController

if _TEXTUAL_OK:

    class TreeMixin(AppBase):
        """Tree event handlers kept on the app; behaviour lives in TreeController."""

        def on_tree_node_selected(self, e: Tree.NodeSelected) -> None:
            """Clicks and cursor moves select only; enter/double-click open detail."""
            self.tree_controller.track(e.node)

        def on_tree_node_highlighted(self, e: Tree.NodeHighlighted) -> None:
            self.tree_controller.track(e.node)

        def on_tree_node_expanded(self, e: Tree.NodeExpanded) -> None:
            self.tree_controller.on_expanded(e.node)

        def on_tree_node_collapsed(self, e: Tree.NodeCollapsed) -> None:
            self.tree_controller.on_collapsed(e.node)

        @staticmethod
        def _node_key(node: TreeNode) -> tuple[str, int] | None:
            return TreeController.node_key(node)

        def _paint_mark(self, key: tuple[str, int]) -> None:
            self.tree_controller.paint_mark(key)

        def _poll(self) -> None:
            self.tree_controller.poll()

        def action_fold(self) -> None:
            self.tree_controller.fold_one()

        def action_fold_all(self) -> None:
            self.tree_controller.fold_all()

        def refresh_all(self, note: str = "") -> None:
            self.tree_controller.refresh_all(note)
