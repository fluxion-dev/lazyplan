"""Build the source trail tree from one loaded trail and cached stats."""

from __future__ import annotations

from collections.abc import Mapping

from textual.widgets import Tree
from textual.widgets.tree import TreeNode

from lazyplan.services.source import (
    CommitStats,
    FileStat,
    SourceCommit,
    SourceFile,
    SourceRepo,
    SourceTrail,
)

from ..views.source import (
    commit_data,
    commit_label,
    commit_matches,
    file_data,
    file_label,
    pull_data,
    pull_label,
    repo_data,
    repo_label,
    repo_matches,
)


def build_trail_tree(
    tree: Tree,
    trail: SourceTrail,
    stats: Mapping[tuple[str, str], CommitStats],
    needle: str,
    commit_nodes: dict[tuple[str, str], TreeNode],
) -> None:
    """Paint every repo, commit, file, and pull that matches *needle*."""
    tree.clear()
    tree.root.expand()
    commit_nodes.clear()
    if trail.empty:
        tree.root.add_leaf(
            "No source linked. Run `lpui link`, `lpui task finish`, or `pr refresh`.",
            data={"kind": "empty", "copy": ""},
        )
        return
    for repo in trail.repos:
        if needle and not repo_matches(repo, needle):
            continue
        _add_repo(tree, repo, stats, needle, commit_nodes)
    if not tree.root.children:
        tree.root.add_leaf(
            f"No source matches {needle!r}.",
            data={"kind": "empty", "copy": ""},
        )


def _add_repo(
    tree: Tree,
    repo: SourceRepo,
    stats: Mapping[tuple[str, str], CommitStats],
    needle: str,
    commit_nodes: dict[tuple[str, str], TreeNode],
) -> None:
    """Add one repo node, its commits, and its pull requests."""
    repo_node = tree.root.add(repo_label(repo), data=repo_data(repo))
    for commit in repo.commits:
        if needle and not commit_matches(commit, needle):
            continue
        _add_commit(repo_node, repo, commit, stats, needle, commit_nodes)
    for pull in repo.pulls:
        if needle and needle not in f"pr {pull.number} {pull.title}".lower():
            continue
        repo_node.add_leaf(pull_label(pull), data=pull_data(repo, pull))
    repo_node.expand()


def _add_commit(
    repo_node: TreeNode,
    repo: SourceRepo,
    commit: SourceCommit,
    stats: Mapping[tuple[str, str], CommitStats],
    needle: str,
    commit_nodes: dict[tuple[str, str], TreeNode],
) -> None:
    """Add one commit and its file rows, using cached stats when known."""
    key = (repo.path, commit.sha)
    cached = stats.get(key)
    by_path = (
        {item.path: item for item in cached.files}
        if cached is not None and cached.state == "ok"
        else {}
    )
    commit_node = repo_node.add(commit_label(commit, cached), data=commit_data(repo, commit))
    commit_nodes[key] = commit_node
    _add_file_rows(commit_node, repo, commit, by_path, needle)
    if not commit.files and not by_path:
        commit_node.add_leaf(
            "[dim]…[/]",
            data={"kind": "placeholder", "copy": ""},
        )


def _add_file_rows(
    commit_node: TreeNode,
    repo: SourceRepo,
    commit: SourceCommit,
    by_path: dict[str, FileStat],
    needle: str,
) -> None:
    """Add cached file rows and any stats-only paths."""
    seen: set[str] = set()
    for item in commit.files:
        if needle and needle not in item.path.lower():
            continue
        stat = by_path.get(item.path)
        seen.add(item.path)
        commit_node.add_leaf(
            file_label(item, stat),
            data=file_data(repo, commit, item, stat),
        )
    for stat in by_path.values():
        if stat.path in seen:
            continue
        item = SourceFile(path=stat.path)
        commit_node.add_leaf(
            file_label(item, stat),
            data=file_data(repo, commit, item, stat),
        )
