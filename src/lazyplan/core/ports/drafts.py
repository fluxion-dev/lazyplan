"""The draft repository port: drafts, revisions, and anchored annotations."""

from __future__ import annotations

from typing import Protocol

from ..entities import DraftAnnotation, DraftRevision, PlanDraft
from .planning import PlanningPort


class DraftsPort(PlanningPort, Protocol):
    """Draft persistence used by the draft use cases."""

    def add_draft(
        self,
        title: str,
        document: str,
        actor: str = "human",
        status: str = "review",
        now: float | None = None,
    ) -> PlanDraft: ...

    def get_draft(self, draft_id: int) -> PlanDraft | None: ...

    def list_drafts(self, status: str = "all") -> list[PlanDraft]: ...

    def add_draft_revision(
        self,
        draft_id: int,
        document: str,
        actor: str = "human",
        note: str = "",
        title: str = "",
        expected_revision: int | None = None,
        now: float | None = None,
    ) -> tuple[PlanDraft, DraftRevision]: ...

    def get_draft_revision(self, draft_id: int, revision: int) -> DraftRevision | None: ...

    def list_draft_revisions(self, draft_id: int) -> list[DraftRevision]: ...

    def set_draft_status(
        self, draft_id: int, status: str, actor: str = "human", now: float | None = None
    ) -> PlanDraft | None: ...

    def link_draft_plan(
        self, draft_id: int, plan_id: int, actor: str = "human", now: float | None = None
    ) -> PlanDraft | None: ...

    def delete_draft(self, draft_id: int, actor: str = "human") -> bool: ...

    def add_draft_annotation(
        self,
        draft_id: int,
        block_key: str,
        kind: str,
        body: str,
        *,
        quote: str = "",
        start_offset: int = 0,
        end_offset: int = 0,
        revision: int | None = None,
        author: str = "human",
        now: float | None = None,
    ) -> DraftAnnotation: ...

    def get_draft_annotation(self, annotation_id: int) -> DraftAnnotation | None: ...

    def list_draft_annotations(
        self, draft_id: int, status: str = "all"
    ) -> list[DraftAnnotation]: ...

    def update_draft_annotation(
        self,
        annotation_id: int,
        actor: str = "human",
        *,
        status: str | None = None,
        response: str | None = None,
        responded_by: str | None = None,
        responded_at: float | None = None,
        anchor_state: str | None = None,
        start_offset: int | None = None,
        end_offset: int | None = None,
    ) -> DraftAnnotation | None: ...

    def delete_draft_annotation(self, annotation_id: int, actor: str = "human") -> bool: ...

    def draft_annotation_counts(self, draft_id: int) -> tuple[int, int]: ...

    def draft_annotation_counts_map(self) -> dict[int, tuple[int, int]]: ...
