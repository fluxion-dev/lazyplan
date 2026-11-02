"""Collaboration use cases: notes, comments, mentions, and resolution."""

from __future__ import annotations

from ..core.entities import Comment, Note
from ..core.ports.collaboration import CollaborationPort


def add_note(
    port: CollaborationPort,
    parent_kind: str,
    parent_id: int,
    text: str,
    actor: str = "human",
) -> Note:
    """Append a handoff note."""
    return port.add_note(parent_kind, parent_id, text, actor=actor)


def list_notes(
    port: CollaborationPort,
    parent_kind: str,
    parent_id: int,
    limit: int | None = None,
) -> list[Note]:
    """Notes on one row, oldest first."""
    return port.list_notes(parent_kind, parent_id, limit=limit)


def notes_map(port: CollaborationPort) -> dict[tuple[str, int], list[str]]:
    """Every note body grouped by parent, for search."""
    return port.notes_map()


def notes_full_map(port: CollaborationPort) -> dict[tuple[str, int], list[Note]]:
    """Every note grouped by parent, with metadata."""
    return port.notes_full_map()


def add_comment(
    port: CollaborationPort,
    parent_kind: str,
    parent_id: int,
    text: str,
    actor: str = "human",
) -> Comment:
    """Append a review comment."""
    return port.add_comment(parent_kind, parent_id, text, actor=actor)


def list_comments(
    port: CollaborationPort,
    parent_kind: str,
    parent_id: int,
    mentions: str | None = None,
) -> list[Comment]:
    """Comments on one row, optionally filtered to one mention."""
    return port.list_comments(parent_kind, parent_id, mentions=mentions)


def comments_map(port: CollaborationPort) -> dict[tuple[str, int], list[str]]:
    """Every comment body grouped by parent, for search."""
    return port.comments_map()


def comments_full_map(port: CollaborationPort) -> dict[tuple[str, int], list[Comment]]:
    """Every comment grouped by parent, with metadata."""
    return port.comments_full_map()


def resolve_comment(
    port: CollaborationPort,
    comment_id: int,
    resolved: bool = True,
    actor: str = "human",
) -> Comment | None:
    """Set or clear a comment's resolved flag."""
    return port.resolve_comment(comment_id, resolved=resolved, actor=actor)


__all__ = [
    "add_comment",
    "add_note",
    "comments_full_map",
    "comments_map",
    "list_comments",
    "list_notes",
    "notes_full_map",
    "notes_map",
    "resolve_comment",
]
