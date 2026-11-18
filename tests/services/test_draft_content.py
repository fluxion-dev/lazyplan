"""Draft blocks and quote anchors over validated plan documents."""

from __future__ import annotations

import os
import tempfile
import unittest

from lazyplan.core.kinds import ANCHOR_MOVED, ANCHOR_OK, ANCHOR_ORPHANED
from lazyplan.services.draft_content import (
    ANCHOR_DUPLICATE,
    ANCHOR_MISSING,
    ANCHOR_UNIQUE,
    AnchorMatch,
    AnchorUpdate,
    DraftBlock,
    DraftContentError,
    blocks_by_key,
    build_blocks,
    reanchor_quote,
    resolve_anchor,
    resolve_quote,
)
from lazyplan.services.plan_document import validate_document
from lazyplan.store import Store


def document() -> dict:
    return {
        "plan": {
            "key": "demo-plan",
            "title": "Demo plan",
            "why": "Why this matters.",
            "what": "## Scope\n\n- One thing.",
            "criteria": ["Works."],
        },
        "milestones": [
            {
                "key": "build",
                "title": "Build it",
                "desc": "As a user, I want the change.",
                "criteria": ["Built."],
                "tasks": [
                    {
                        "key": "impl",
                        "title": "Implement it",
                        "desc": "Approach: do the work.",
                        "criteria": ["Tests pass."],
                    }
                ],
            }
        ],
    }


class DraftContentTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(os.path.join(self.tmp.name, "t.db"))
        self.document = validate_document(self.store, document())

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_blocks_are_ordered_keyed_and_unique(self) -> None:
        blocks = build_blocks(self.document)
        self.assertEqual(
            [block.key for block in blocks],
            [
                "plan:title",
                "plan:why",
                "plan:what",
                "plan:settings",
                "plan:criterion:0",
                "milestone:build",
                "milestone:build:desc",
                "milestone:build:settings",
                "milestone:build:criterion:0",
                "task:impl",
                "task:impl:desc",
                "task:impl:role",
                "task:impl:criterion:0",
            ],
        )
        self.assertEqual(len(blocks), len({block.key for block in blocks}))
        self.assertTrue(all(block.text.strip() for block in blocks))

    def test_block_text_labels_and_levels(self) -> None:
        blocks = blocks_by_key(build_blocks(self.document))
        self.assertEqual(blocks["plan:title"].text, "Demo plan")
        self.assertEqual(blocks["plan:why"].text, "Why this matters.")
        self.assertIn("key: demo-plan", blocks["plan:settings"].text)
        self.assertIn("dispatch: serial", blocks["plan:settings"].text)
        self.assertEqual(blocks["milestone:build"].text, "Build it")
        self.assertEqual(blocks["milestone:build"].kind, "title")
        self.assertEqual(blocks["milestone:build"].level, 1)
        self.assertIn("lane group: 1", blocks["milestone:build:settings"].text)
        self.assertEqual(blocks["task:impl"].text, "Implement it")
        self.assertEqual(blocks["task:impl"].level, 2)
        self.assertEqual(blocks["task:impl:role"].text, "role: implementer")
        self.assertEqual(blocks["plan:criterion:0"].kind, "criterion")
        self.assertIn("criterion 1", blocks["plan:criterion:0"].label)

    def test_blocks_by_key_refuses_duplicates(self) -> None:
        block = DraftBlock("plan:why", "Why", "Text")
        with self.assertRaises(DraftContentError):
            blocks_by_key([block, block])

    def test_invalid_block_is_refused(self) -> None:
        with self.assertRaises(DraftContentError):
            DraftBlock("plan:why", "Why", "  ")
        with self.assertRaises(DraftContentError):
            DraftBlock("  ", "Why", "Text")
        with self.assertRaises(DraftContentError):
            DraftBlock("plan:why", "Why", "Text", kind="bogus")
        with self.assertRaises(DraftContentError):
            DraftBlock("plan:why", "Why", "Text", level=-1)

    def test_resolve_quote(self) -> None:
        self.assertEqual(resolve_quote("alpha beta", "beta"), AnchorMatch(ANCHOR_UNIQUE, 6, 10))
        self.assertEqual(resolve_quote("alpha", ""), AnchorMatch(ANCHOR_UNIQUE, 0, 0))
        self.assertEqual(resolve_quote("same same", "same").state, ANCHOR_DUPLICATE)
        self.assertEqual(resolve_quote("alpha", "gamma").state, ANCHOR_MISSING)

    def test_resolve_anchor(self) -> None:
        blocks = build_blocks(self.document)
        self.assertEqual(
            resolve_anchor(blocks, "plan:why", "matters"),
            AnchorMatch(ANCHOR_UNIQUE, 9, 16),
        )
        self.assertEqual(resolve_anchor(blocks, "plan:why", "missing").state, ANCHOR_MISSING)
        self.assertEqual(resolve_anchor(blocks, "missing:block", "text").state, ANCHOR_MISSING)

    def test_reanchor_quote(self) -> None:
        self.assertEqual(
            reanchor_quote("alpha beta", "beta", 6, 10),
            AnchorUpdate(ANCHOR_OK, 6, 10),
        )
        self.assertEqual(
            reanchor_quote("x alpha beta", "beta", 6, 10),
            AnchorUpdate(ANCHOR_MOVED, 8, 12),
        )
        self.assertEqual(
            reanchor_quote("alpha", "beta", 6, 10),
            AnchorUpdate(ANCHOR_ORPHANED, 6, 10),
        )
        self.assertEqual(
            reanchor_quote("beta beta", "beta", 5, 9),
            AnchorUpdate(ANCHOR_ORPHANED, 5, 9),
        )
        self.assertEqual(
            reanchor_quote("alpha", "", 0, 0),
            AnchorUpdate(ANCHOR_OK, 0, 0),
        )

    def test_anchor_update_validates(self) -> None:
        with self.assertRaises(DraftContentError):
            AnchorUpdate("bogus", 0, 0)
        with self.assertRaises(DraftContentError):
            AnchorUpdate(ANCHOR_OK, 5, 4)
