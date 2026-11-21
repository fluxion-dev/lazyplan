"""Shared JSON payloads for draft MCP tools and resources."""

from __future__ import annotations

import json

from ...core.entities import DraftAnnotation, PlanDraft
from ...core.ports.app import AppPort
from ...core.serialization import to_payload
from ...services import drafts as draft_services
from ...services.drafts import DraftDetail, DraftPromotion


def draft_payload(draft: PlanDraft, open_count: int, total_count: int) -> dict:
    """One draft with its annotation counts."""
    payload = to_payload(vars(draft))
    payload["open_annotations"] = open_count
    payload["total_annotations"] = total_count
    return payload


def annotation_payload(annotation: DraftAnnotation) -> dict:
    """One annotation and its anchor."""
    return to_payload(vars(annotation))


def detail_payload(detail: DraftDetail) -> dict:
    """One draft's content, blocks, and annotations."""
    draft = detail.draft
    payload = {
        "draft": draft_payload(draft, detail.open_annotations, detail.total_annotations),
        "blocks": [vars(block) for block in detail.blocks],
        "annotations": [annotation_payload(row) for row in detail.annotations],
    }
    if draft.format == "sketch":
        payload["sketch"] = draft.document
    else:
        payload["document"] = json.loads(draft.document)
    return payload


def promotion_payload(promotion: DraftPromotion, open_count: int, total_count: int) -> dict:
    """One promotion result with the created or existing plan."""
    return {
        "draft": draft_payload(promotion.draft, open_count, total_count),
        "plan": to_payload(vars(promotion.plan)),
        "created": promotion.created,
        "counts": promotion.counts,
    }


def drafts_payload(store: AppPort) -> list[dict]:
    """Every draft with its annotation counts."""
    counts = draft_services.annotation_counts_map(store)
    return [
        draft_payload(draft, *counts.get(draft.id, (0, 0)))
        for draft in draft_services.list_drafts(store)
    ]
