"""Deterministic draft blocks and quote anchors over plan documents."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from ..core.kinds import ANCHOR_MOVED, ANCHOR_OK, ANCHOR_ORPHANED, DRAFT_ANCHOR_STATES
from .plan_document import MilestoneDocument, PlanDocument, TaskDocument

BLOCK_TITLE = "title"
BLOCK_TEXT = "text"
BLOCK_SETTINGS = "settings"
BLOCK_CRITERION = "criterion"
BLOCK_KINDS: tuple[str, str, str, str] = (
    BLOCK_TITLE,
    BLOCK_TEXT,
    BLOCK_SETTINGS,
    BLOCK_CRITERION,
)

ANCHOR_UNIQUE = "unique"
ANCHOR_DUPLICATE = "duplicate"
ANCHOR_MISSING = "missing"
ANCHOR_STATES: tuple[str, str, str] = (ANCHOR_UNIQUE, ANCHOR_DUPLICATE, ANCHOR_MISSING)


class DraftContentError(ValueError):
    """A draft document cannot be rendered as annotated blocks."""


@dataclass(frozen=True)
class DraftBlock:
    """One selectable part of a draft document."""

    key: str
    label: str
    text: str
    kind: str = BLOCK_TEXT
    level: int = 0

    def __post_init__(self) -> None:
        if not self.key.strip():
            raise DraftContentError("block key must not be empty")
        if not self.label.strip():
            raise DraftContentError(f"block {self.key!r} has no label")
        if not self.text.strip():
            raise DraftContentError(f"block {self.key!r} has no text")
        if self.kind not in BLOCK_KINDS:
            raise DraftContentError(f"block {self.key!r} kind must be {'|'.join(BLOCK_KINDS)}")
        if self.level < 0:
            raise DraftContentError(f"block {self.key!r} level must not be negative")


@dataclass(frozen=True)
class AnchorMatch:
    """The result of finding one quote inside a block's text."""

    state: str
    start: int = 0
    end: int = 0

    def __post_init__(self) -> None:
        if self.state not in ANCHOR_STATES:
            raise DraftContentError(f"anchor state must be {'|'.join(ANCHOR_STATES)}")
        if self.start < 0 or self.end < self.start:
            raise DraftContentError("anchor offsets must be a valid range")


@dataclass(frozen=True)
class AnchorUpdate:
    """How one stored annotation tracked its quote after a revision."""

    state: str
    start_offset: int
    end_offset: int

    def __post_init__(self) -> None:
        if self.state not in DRAFT_ANCHOR_STATES:
            raise DraftContentError(
                f"annotation anchor state must be {'|'.join(DRAFT_ANCHOR_STATES)}"
            )
        if self.start_offset < 0 or self.end_offset < self.start_offset:
            raise DraftContentError("annotation offsets must be a valid range")


def _milestone_blocks(milestone: MilestoneDocument) -> list[DraftBlock]:
    """Every block under one milestone, in reading order."""
    label = f"Milestone {milestone.key}"
    blocks = [
        DraftBlock(
            f"milestone:{milestone.key}",
            f"{label} title",
            milestone.title,
            kind=BLOCK_TITLE,
            level=1,
        ),
        DraftBlock(
            f"milestone:{milestone.key}:desc",
            f"{label} description",
            milestone.description,
            level=1,
        ),
        DraftBlock(
            f"milestone:{milestone.key}:settings",
            f"{label} settings",
            f"lane group: {milestone.lane_group} · role: {milestone.agent_role}",
            kind=BLOCK_SETTINGS,
            level=1,
        ),
    ]
    for index, criterion in enumerate(milestone.criteria):
        blocks.append(
            DraftBlock(
                f"milestone:{milestone.key}:criterion:{index}",
                f"{label} criterion {index + 1}",
                criterion,
                kind=BLOCK_CRITERION,
                level=1,
            )
        )
    for task in milestone.tasks:
        blocks.extend(_task_blocks(task))
    return blocks


def _task_blocks(task: TaskDocument) -> list[DraftBlock]:
    """Every block under one task, in reading order."""
    label = f"Task {task.key}"
    blocks = [
        DraftBlock(
            f"task:{task.key}",
            f"{label} title",
            task.title,
            kind=BLOCK_TITLE,
            level=2,
        ),
        DraftBlock(
            f"task:{task.key}:desc",
            f"{label} description",
            task.description,
            level=2,
        ),
        DraftBlock(
            f"task:{task.key}:role",
            f"{label} role",
            f"role: {task.role}",
            kind=BLOCK_SETTINGS,
            level=2,
        ),
    ]
    for index, criterion in enumerate(task.criteria):
        blocks.append(
            DraftBlock(
                f"task:{task.key}:criterion:{index}",
                f"{label} criterion {index + 1}",
                criterion,
                kind=BLOCK_CRITERION,
                level=2,
            )
        )
    return blocks


def build_blocks(document: PlanDocument) -> tuple[DraftBlock, ...]:
    """Render one validated document as ordered, keyed blocks."""
    blocks = [
        DraftBlock("plan:title", "Plan title", document.title, kind=BLOCK_TITLE),
        DraftBlock("plan:why", "Plan why", document.why),
        DraftBlock("plan:what", "Plan what", document.what),
        DraftBlock(
            "plan:settings",
            "Plan settings",
            (
                f"key: {document.key} · dispatch: {document.dispatch_mode}"
                f" · max agents: {document.max_agents}"
            ),
            kind=BLOCK_SETTINGS,
        ),
    ]
    for index, criterion in enumerate(document.criteria):
        blocks.append(
            DraftBlock(
                f"plan:criterion:{index}",
                f"Acceptance criterion {index + 1}",
                criterion,
                kind=BLOCK_CRITERION,
            )
        )
    for milestone in document.milestones:
        blocks.extend(_milestone_blocks(milestone))
    return tuple(blocks)


def blocks_by_key(blocks: Iterable[DraftBlock]) -> dict[str, DraftBlock]:
    """Index blocks by key, refusing duplicates."""
    indexed: dict[str, DraftBlock] = {}
    for block in blocks:
        if block.key in indexed:
            raise DraftContentError(f"duplicate block key: {block.key}")
        indexed[block.key] = block
    return indexed


def resolve_quote(text: str, quote: str) -> AnchorMatch:
    """Find *quote* in *text* as unique, duplicate, or missing."""
    if not quote:
        return AnchorMatch(ANCHOR_UNIQUE, 0, 0)
    first = text.find(quote)
    if first < 0:
        return AnchorMatch(ANCHOR_MISSING)
    second = text.find(quote, first + len(quote))
    end = first + len(quote)
    if second >= 0:
        return AnchorMatch(ANCHOR_DUPLICATE, first, end)
    return AnchorMatch(ANCHOR_UNIQUE, first, end)


def resolve_anchor(blocks: Iterable[DraftBlock], block_key: str, quote: str) -> AnchorMatch:
    """Find a quote inside the named block, or report it missing."""
    block = blocks_by_key(blocks).get(block_key)
    if block is None:
        return AnchorMatch(ANCHOR_MISSING)
    return resolve_quote(block.text, quote)


def reanchor_quote(
    text: str,
    quote: str,
    start_offset: int,
    end_offset: int,
) -> AnchorUpdate:
    """Track one annotation's quote into a block's current text."""
    if not quote:
        return AnchorUpdate(ANCHOR_OK, 0, 0)
    match = resolve_quote(text, quote)
    if match.state != ANCHOR_UNIQUE:
        return AnchorUpdate(ANCHOR_ORPHANED, start_offset, end_offset)
    if (match.start, match.end) == (start_offset, end_offset):
        return AnchorUpdate(ANCHOR_OK, start_offset, end_offset)
    return AnchorUpdate(ANCHOR_MOVED, match.start, match.end)
