"""User-owned tree expansion, filter baselines, and visible-row resolution.

Split from ``tree.py`` and ``reconcile.py`` so one module owns the rule that a
branch only opens or closes when the reader asks, and that navigation never
opens one.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.widgets.tree import TreeNode

if TYPE_CHECKING:
    from ..app import LazyplanApp


class ExpansionMixin:
    """Apply the expansion sets once and resolve rows without opening them."""

    app: LazyplanApp
    _visible_keys: set[tuple[str, int]]
    _loading: bool

    if TYPE_CHECKING:

        def node_key(self, node: TreeNode) -> tuple[str, int] | None: ...

        def has_model_children(self, key: tuple[str, int]) -> bool: ...

        def load_branch(self, node: TreeNode, key: tuple[str, int]) -> None: ...

    def apply_expansion(self, reveal: set[tuple[str, int]] | None = None) -> None:
        """Apply the expansion sets once, parents before children.

        This pass only reflects state; it never records a transition. Events
        posted by ``expand`` and ``collapse`` are ignored by the handlers
        because the node already agrees with the sets.
        """
        app = self.app
        effective = set(app._expanded)
        if reveal:
            effective.update(reveal)
        for kind in ("plan", "milestone"):
            for key in [key for key in app._row_nodes if key[0] == kind]:
                node = app._row_nodes.get(key)
                if node is None or not node.allow_expand:
                    continue
                if key in effective:
                    self.load_branch(node, key)
                    if not node.is_expanded:
                        node.expand()
                elif node.is_expanded:
                    node.collapse()

    def sync_filter_snapshot(self, filtering: bool) -> None:
        """Capture the baseline once per filter run and restore it when it clears."""
        app = self.app
        if filtering:
            if app.state.filter_snapshot is None:
                app.state.filter_snapshot = (set(app._expanded), set(app._collapsed))
            return
        snapshot = app.state.filter_snapshot
        if snapshot is None:
            return
        app._expanded.clear()
        app._expanded.update(snapshot[0])
        app._collapsed.clear()
        app._collapsed.update(snapshot[1])
        app.state.filter_snapshot = None

    def reveal_keys(self) -> set[tuple[str, int]]:
        """Branches the active filter may open without touching the baseline."""
        return {key for key in self._visible_keys if self.has_model_children(key)}

    def ancestor_keys(self, node: TreeNode) -> list[tuple[str, int]]:
        """Keys from a node's nearest parent up to the root, hidden rows included."""
        keys: list[tuple[str, int]] = []
        parent = node.parent
        while parent is not None:
            key = self.node_key(parent)
            if key is not None:
                keys.append(key)
            parent = parent.parent
        return keys

    def is_visible(self, node: TreeNode) -> bool:
        """True when the row's tree and every ancestor are open."""
        if not node.tree.display:
            return False
        parent = node.parent
        while parent is not None:
            if not parent.is_expanded:
                return False
            parent = parent.parent
        return True

    def visible_key(self, key: tuple[str, int]) -> tuple[str, int] | None:
        """The row itself or its nearest visible ancestor; never opens a branch."""
        node = self.app._row_nodes.get(key)
        while node is not None:
            if self.is_visible(node):
                return self.node_key(node)
            node = node.parent
        return None

    def on_expanded(self, node: TreeNode) -> None:
        """Record a user expansion only; applied expansions already agree."""
        if self._loading or self.app.state.filter_snapshot is not None:
            return
        key = self.node_key(node)
        if key is None or key[0] not in ("plan", "milestone"):
            return
        if key in self.app._expanded:
            return
        self.app._expanded.add(key)
        self.app._collapsed.discard(key)
        self.load_branch(node, key)

    def on_collapsed(self, node: TreeNode) -> None:
        """Record a user collapse only; applied collapses already agree."""
        if self.app.state.filter_snapshot is not None:
            return
        key = self.node_key(node)
        if key is None or key[0] not in ("plan", "milestone"):
            return
        if key not in self.app._expanded:
            return
        self.app._expanded.discard(key)
        self.app._collapsed.add(key)


__all__ = ["ExpansionMixin"]
