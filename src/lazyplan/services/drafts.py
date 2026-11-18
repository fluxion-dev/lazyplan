"""Draft use cases: create, review, annotate, revise, and promote."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

from ..core.entities import DraftAnnotation, Plan, PlanDraft
from ..core.ports.drafts import DraftsPort
from . import plan_apply
from .draft_content import (
    ANCHOR_DUPLICATE,
    ANCHOR_MISSING,
    DraftBlock,
    blocks_by_key,
    build_blocks,
    resolve_quote,
)
from .plan_document import PlanDocument, load_normalized, to_json, validate_document


@dataclass(frozen=True)
class DraftDetail:
    """One draft with its document, blocks, and annotations."""

    draft: PlanDraft
    document: PlanDocument
    blocks: tuple[DraftBlock, ...]
    annotations: tuple[DraftAnnotation, ...]
    open_annotations: int
    total_annotations: int


@dataclass(frozen=True)
class DraftPromotion:
    """The plan a draft created, or the plan it already created."""

    draft: PlanDraft
    plan: Plan
    created: bool
    counts: dict[str, int]


def _require_draft(port: DraftsPort, draft_id: int) -> PlanDraft:
    """Fetch one draft or name the missing id."""
    draft = port.get_draft(draft_id)
    if draft is None:
        raise KeyError(f"draft #{draft_id} not found")
    return draft


def _require_annotation(port: DraftsPort, annotation_id: int) -> DraftAnnotation:
    """Fetch one annotation or name the missing id."""
    annotation = port.get_draft_annotation(annotation_id)
    if annotation is None:
        raise KeyError(f"annotation #{annotation_id} not found")
    return annotation


def _document(draft: PlanDraft) -> PlanDocument:
    """Rebuild the stored normalized document without template drift."""
    try:
        raw = json.loads(draft.document)
    except json.JSONDecodeError as exc:
        raise ValueError(f"draft #{draft.id} has an unreadable document: {exc}") from exc
    return load_normalized(raw)


def _ensure_plan_key_free(port: DraftsPort, key: str) -> None:
    """Refuse a plan key that already belongs to a plan."""
    existing = port.get_entity_key("plan", key)
    if existing is not None:
        raise ValueError(f"plan key {key!r} already belongs to plan #{existing}")


def _plan_counts(port: DraftsPort, plan_id: int) -> dict[str, int]:
    """Row counts for one plan tree."""
    milestones = port.list_milestones(plan_id)
    tasks = 0
    criteria = len(port.list_criteria("plan", plan_id))
    for milestone in milestones:
        criteria += len(port.list_criteria("milestone", milestone.id))
        for task in port.list_tasks(milestone.id):
            tasks += 1
            criteria += len(port.list_criteria("task", task.id))
    return {"milestones": len(milestones), "tasks": tasks, "criteria": criteria}


def create(port: DraftsPort, raw: Any, actor: str = "human") -> PlanDraft:
    """Validate a plan document and store it as a new draft."""
    document = validate_document(port, raw)
    _ensure_plan_key_free(port, document.key)
    return port.add_draft(document.title, to_json(document), actor=actor)


def list_drafts(port: DraftsPort, status: str = "all") -> list[PlanDraft]:
    """Drafts in creation order, optionally by status."""
    return port.list_drafts(status)


def detail(port: DraftsPort, draft_id: int) -> DraftDetail:
    """One draft with its blocks and annotations."""
    draft = _require_draft(port, draft_id)
    document = _document(draft)
    rows = tuple(port.list_draft_annotations(draft.id))
    open_count = sum(1 for annotation in rows if annotation.status == "open")
    return DraftDetail(
        draft=draft,
        document=document,
        blocks=build_blocks(document),
        annotations=rows,
        open_annotations=open_count,
        total_annotations=len(rows),
    )


def list_annotations(port: DraftsPort, draft_id: int, status: str = "all") -> list[DraftAnnotation]:
    """Annotations for one draft, optionally filtered by state."""
    _require_draft(port, draft_id)
    return port.list_draft_annotations(draft_id, status)


def revise(
    port: DraftsPort,
    draft_id: int,
    raw: Any,
    base_revision: int,
    actor: str = "human",
    note: str = "",
) -> PlanDraft:
    """Replace the document with a validated revision of the same draft."""
    draft = _require_draft(port, draft_id)
    if draft.status == "promoted":
        raise ValueError(f"draft #{draft_id} is promoted; it cannot be revised")
    if base_revision != draft.revision:
        raise ValueError(f"draft #{draft_id} is at revision {draft.revision}, not {base_revision}")
    document = validate_document(port, raw)
    _ensure_plan_key_free(port, document.key)
    text = to_json(document)
    with port.transaction():
        updated, _snapshot = port.add_draft_revision(
            draft.id,
            text,
            actor=actor,
            note=note,
            title=document.title,
            expected_revision=base_revision,
        )
        if updated.status != "review":
            updated = port.set_draft_status(draft.id, "review", actor=actor) or updated
    return updated


def submit(port: DraftsPort, draft_id: int, actor: str = "human") -> PlanDraft:
    """Submit open feedback and move the draft to revising."""
    draft = _require_draft(port, draft_id)
    if draft.status == "promoted":
        raise ValueError(f"draft #{draft_id} is promoted; it cannot be submitted")
    if draft.status == "revising":
        return draft
    open_annotations = port.list_draft_annotations(draft.id, status="open")
    if not open_annotations:
        raise ValueError(f"draft #{draft_id} has no open annotations to submit")
    updated = port.set_draft_status(draft.id, "revising", actor=actor)
    if updated is None:
        raise KeyError(f"draft #{draft_id} not found")
    return updated


def ready(port: DraftsPort, draft_id: int, actor: str = "human") -> PlanDraft:
    """Return a revised draft to review once no annotations are open."""
    draft = _require_draft(port, draft_id)
    if draft.status == "promoted":
        raise ValueError(f"draft #{draft_id} is promoted; it is already final")
    if draft.status == "review":
        return draft
    open_annotations = port.list_draft_annotations(draft.id, status="open")
    if open_annotations:
        raise ValueError(f"draft #{draft_id} still has {len(open_annotations)} open annotation(s)")
    updated = port.set_draft_status(draft.id, "review", actor=actor)
    if updated is None:
        raise KeyError(f"draft #{draft_id} not found")
    return updated


def _quote_offsets(
    text: str,
    quote: str,
    start_offset: int,
    end_offset: int,
) -> tuple[int, int]:
    """Resolve one quote, honoring exact caller offsets when they match."""
    if (
        quote
        and 0 <= start_offset < end_offset <= len(text)
        and text[start_offset:end_offset] == quote
    ):
        return start_offset, end_offset
    match = resolve_quote(text, quote)
    if match.state == ANCHOR_MISSING:
        raise ValueError(f"quote {quote!r} was not found in the block")
    if match.state == ANCHOR_DUPLICATE:
        raise ValueError(f"quote {quote!r} appears more than once in the block")
    return match.start, match.end


def annotate(
    port: DraftsPort,
    draft_id: int,
    block_key: str,
    kind: str,
    body: str,
    *,
    quote: str = "",
    start_offset: int = 0,
    end_offset: int = 0,
    author: str = "human",
) -> DraftAnnotation:
    """Attach one comment, question, or change to a draft block."""
    draft = _require_draft(port, draft_id)
    if draft.status == "promoted":
        raise ValueError(f"draft #{draft_id} is promoted; annotations are read-only")
    blocks = blocks_by_key(build_blocks(_document(draft)))
    block = blocks.get(block_key)
    if block is None:
        raise ValueError(f"block {block_key!r} not found in draft #{draft_id}")
    start, end = _quote_offsets(block.text, quote, start_offset, end_offset)
    return port.add_draft_annotation(
        draft.id,
        block.key,
        kind,
        body,
        quote=quote,
        start_offset=start,
        end_offset=end,
        revision=draft.revision,
        author=author,
    )


def _annotation_draft(port: DraftsPort, annotation: DraftAnnotation) -> PlanDraft:
    """The draft an annotation belongs to, refusing promoted edits."""
    draft = _require_draft(port, annotation.draft_id)
    if draft.status == "promoted":
        raise ValueError(f"draft #{draft.id} is promoted; annotations are read-only")
    return draft


def respond(
    port: DraftsPort,
    annotation_id: int,
    response: str,
    actor: str = "human",
    now: float | None = None,
) -> DraftAnnotation:
    """Answer one annotation and mark it addressed."""
    annotation = _require_annotation(port, annotation_id)
    _annotation_draft(port, annotation)
    if annotation.status == "dismissed":
        raise ValueError(f"annotation #{annotation_id} is dismissed")
    body = response.strip()
    if not body:
        raise ValueError("a response must not be empty")
    stamp = time.time() if now is None else now
    updated = port.update_draft_annotation(
        annotation.id,
        actor=actor,
        status="addressed",
        response=body,
        responded_by=actor,
        responded_at=stamp,
    )
    if updated is None:
        raise KeyError(f"annotation #{annotation_id} not found")
    return updated


def resolve(
    port: DraftsPort,
    annotation_id: int,
    response: str = "",
    actor: str = "human",
    now: float | None = None,
) -> DraftAnnotation:
    """Mark one annotation addressed, with an optional response."""
    annotation = _require_annotation(port, annotation_id)
    _annotation_draft(port, annotation)
    if annotation.status == "dismissed":
        raise ValueError(f"annotation #{annotation_id} is dismissed")
    stamp = time.time() if now is None else now
    updated = port.update_draft_annotation(
        annotation.id,
        actor=actor,
        status="addressed",
        response=response.strip(),
        responded_by=actor,
        responded_at=stamp,
    )
    if updated is None:
        raise KeyError(f"annotation #{annotation_id} not found")
    return updated


def dismiss(
    port: DraftsPort,
    annotation_id: int,
    reason: str = "",
    actor: str = "human",
    now: float | None = None,
) -> DraftAnnotation:
    """Dismiss one annotation without treating it as addressed."""
    annotation = _require_annotation(port, annotation_id)
    _annotation_draft(port, annotation)
    if annotation.status == "dismissed":
        return annotation
    stamp = time.time() if now is None else now
    updated = port.update_draft_annotation(
        annotation.id,
        actor=actor,
        status="dismissed",
        response=reason.strip(),
        responded_by=actor,
        responded_at=stamp,
    )
    if updated is None:
        raise KeyError(f"annotation #{annotation_id} not found")
    return updated


def delete_annotation(port: DraftsPort, annotation_id: int, actor: str = "human") -> bool:
    """Delete one annotation before the draft is promoted."""
    annotation = _require_annotation(port, annotation_id)
    _annotation_draft(port, annotation)
    return port.delete_draft_annotation(annotation.id, actor=actor)


def delete_draft(port: DraftsPort, draft_id: int, actor: str = "human") -> bool:
    """Delete one draft that has not been promoted."""
    draft = _require_draft(port, draft_id)
    if draft.status == "promoted":
        raise ValueError(f"draft #{draft_id} is promoted; it cannot be deleted")
    return port.delete_draft(draft.id, actor=actor)


def promote(port: DraftsPort, draft_id: int, actor: str = "human") -> DraftPromotion:
    """Create the plan tree from a clean draft and link it back."""
    draft = _require_draft(port, draft_id)
    if draft.status == "promoted":
        if draft.plan_id is None:
            raise ValueError(f"draft #{draft_id} is promoted without a plan")
        plan = port.get_plan(draft.plan_id)
        if plan is None:
            raise ValueError(f"draft #{draft_id} points at missing plan #{draft.plan_id}")
        return DraftPromotion(draft, plan, False, _plan_counts(port, plan.id))
    if draft.status != "review":
        raise ValueError(f"draft #{draft_id} is {draft.status}; revise it before promoting")
    open_annotations = port.list_draft_annotations(draft.id, status="open")
    if open_annotations:
        raise ValueError(f"draft #{draft_id} has {len(open_annotations)} open annotation(s)")
    document = _document(draft)
    _ensure_plan_key_free(port, document.key)
    with port.transaction():
        result = plan_apply.apply(port, document, actor=actor)
        plan = result["plan"]
        if not result["created"]:
            raise ValueError(f"plan key {document.key!r} already belongs to plan #{plan.id}")
        linked = port.link_draft_plan(draft.id, plan.id, actor=actor)
        if linked is None:
            raise KeyError(f"draft #{draft_id} not found")
    counts = dict(result["counts"])
    return DraftPromotion(linked, plan, True, counts)
