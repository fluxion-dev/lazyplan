"""The collaboration repository port: notes and comments."""

from __future__ import annotations

from typing import Protocol

from ..entities import Comment, Note


class CollaborationPort(Protocol):
    """Annotation surface used by notes, comments, and search."""

    def add_note(
        self, parent_kind: str, parent_id: int, text: str, actor: str = "human"
    ) -> Note: ...

    def list_notes(
        self, parent_kind: str, parent_id: int, limit: int | None = None
    ) -> list[Note]: ...

    def notes_map(self) -> dict[tuple[str, int], list[str]]: ...

    def notes_full_map(self) -> dict[tuple[str, int], list[Note]]: ...

    def restore_note(
        self,
        parent_kind: str,
        parent_id: int,
        text: str,
        actor: str,
        ts: float,
    ) -> Note | None: ...

    def add_comment(
        self, parent_kind: str, parent_id: int, text: str, actor: str = "human"
    ) -> Comment: ...

    def list_comments(
        self,
        parent_kind: str,
        parent_id: int,
        mentions: str | None = None,
    ) -> list[Comment]: ...

    def comments_map(self) -> dict[tuple[str, int], list[str]]: ...

    def comments_full_map(self) -> dict[tuple[str, int], list[Comment]]: ...

    def resolve_comment(
        self, cid: int, resolved: bool = True, actor: str = "human"
    ) -> Comment | None: ...

    def restore_comment(
        self,
        parent_kind: str,
        parent_id: int,
        text: str,
        actor: str,
        ts: float,
        resolved: bool,
    ) -> Comment | None: ...
