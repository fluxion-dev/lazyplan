"""Sketch draft use cases: create and revise definition-only Markdown."""

from __future__ import annotations

from ..core.entities import PlanDraft
from ..core.kinds import DRAFT_FORMAT_SKETCH
from ..core.ports.drafts import DraftsPort
from .draft_anchors import reanchor
from .draft_content import build_sketch_blocks
from .sketch_document import SketchDocument, parse_sketch, render_sketch


def _require_sketch(port: DraftsPort, draft_id: int) -> PlanDraft:
    """Fetch a sketch draft, refusing a document or a promoted draft."""
    draft = port.get_draft(draft_id)
    if draft is None:
        raise KeyError(f"draft #{draft_id} not found")
    if draft.format != DRAFT_FORMAT_SKETCH:
        raise ValueError(f"draft #{draft_id} is a document, not a sketch")
    if draft.status == "promoted":
        raise ValueError(f"draft #{draft_id} is promoted; it cannot be revised")
    return draft


def create_sketch(port: DraftsPort, text: str, actor: str = "human") -> PlanDraft:
    """Validate Markdown and store it as a sketch draft."""
    sketch = parse_sketch(text)
    return port.add_draft(
        sketch.title,
        render_sketch(sketch),
        actor=actor,
        format=DRAFT_FORMAT_SKETCH,
    )


def create_from_fields(
    port: DraftsPort,
    title: str,
    why: str,
    what: str,
    actor: str = "human",
) -> PlanDraft:
    """Store title, why, and what as a canonical sketch."""
    title = title.strip()
    if not title:
        raise ValueError("title must not be empty")
    if "\n" in title:
        raise ValueError("title must be one line")
    if not why.strip():
        raise ValueError("why must not be empty")
    if not what.strip():
        raise ValueError("what must not be empty")
    sketch = SketchDocument(title, why.strip(), what.strip())
    return create_sketch(port, render_sketch(sketch), actor=actor)


def revise_sketch(
    port: DraftsPort,
    draft_id: int,
    text: str,
    base_revision: int,
    actor: str = "human",
    note: str = "",
) -> PlanDraft:
    """Replace a sketch with a validated revision of the same draft."""
    draft = _require_sketch(port, draft_id)
    if base_revision != draft.revision:
        raise ValueError(f"draft #{draft_id} is at revision {draft.revision}, not {base_revision}")
    sketch = parse_sketch(text)
    blocks = build_sketch_blocks(sketch)
    with port.transaction():
        updated, _snapshot = port.add_draft_revision(
            draft.id,
            render_sketch(sketch),
            actor=actor,
            note=note,
            title=sketch.title,
            expected_revision=base_revision,
            format=DRAFT_FORMAT_SKETCH,
        )
        reanchor(port, updated, blocks, actor)
        if updated.status != "review":
            updated = port.set_draft_status(draft.id, "review", actor=actor) or updated
    return updated
