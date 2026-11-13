"""Tree navigation helpers for the read-only source screen."""

from __future__ import annotations

from textual.widgets import Tree
from textual.widgets.tree import TreeNode


def file_nodes(tree: Tree) -> tuple[TreeNode | None, TreeNode | None, list[TreeNode]]:
    """Current node, its commit node, and the commit's file rows."""
    node = tree.cursor_node
    data = node.data if node is not None else None
    if not isinstance(data, dict):
        return node, None, []
    kind = str(data.get("kind", ""))
    if kind == "file" and node is not None:
        commit_node = node.parent
    elif kind == "commit":
        commit_node = node
    else:
        return node, None, []
    if commit_node is None:
        return node, None, []
    files = [
        child
        for child in commit_node.children
        if isinstance(child.data, dict) and child.data.get("kind") == "file"
    ]
    return node, commit_node, files
