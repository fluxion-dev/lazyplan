"""Selectable draft document rows: a label plus its exact block text."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

from ....services.draft_content import DraftBlock


class DraftBlockBody(Static):
    """The exact text of one draft block; selection offsets point into it."""

    can_focus = True

    def __init__(self, block: DraftBlock) -> None:
        super().__init__(block.text, markup=False, classes="draft-block-body")
        self.block = block


class DraftBlockView(Vertical):
    """One labelled draft block with a focusable body."""

    def __init__(self, block: DraftBlock) -> None:
        super().__init__(classes=f"draft-block level-{block.level}")
        self.block = block

    def compose(self) -> ComposeResult:
        yield Static(
            f"{self.block.label} [{self.block.kind}]",
            markup=False,
            classes="draft-block-label",
        )
        yield DraftBlockBody(self.block)
