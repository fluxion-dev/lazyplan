"""Track draft annotations into revised blocks of either format."""

from __future__ import annotations

from ..core.entities import PlanDraft
from ..core.kinds import ANCHOR_ORPHANED
from ..core.ports.drafts import DraftsPort
from .draft_content import AnchorUpdate, DraftBlock, blocks_by_key, reanchor_quote


def reanchor(
    port: DraftsPort,
    draft: PlanDraft,
    blocks: tuple[DraftBlock, ...],
    actor: str,
) -> None:
    """Track every live annotation into revised blocks."""
    indexed = blocks_by_key(blocks)
    for annotation in port.list_draft_annotations(draft.id):
        if annotation.status == "dismissed":
            continue
        block = indexed.get(annotation.block_key)
        if block is None:
            update = AnchorUpdate(ANCHOR_ORPHANED, annotation.start_offset, annotation.end_offset)
        else:
            update = reanchor_quote(
                block.text,
                annotation.quote,
                annotation.start_offset,
                annotation.end_offset,
            )
        current = (
            annotation.anchor_state,
            annotation.start_offset,
            annotation.end_offset,
        )
        if current == (update.state, update.start_offset, update.end_offset):
            continue
        changed = port.update_draft_annotation(
            annotation.id,
            actor=actor,
            anchor_state=update.state,
            start_offset=update.start_offset,
            end_offset=update.end_offset,
        )
        if changed is None:
            raise KeyError(f"annotation #{annotation.id} not found")
