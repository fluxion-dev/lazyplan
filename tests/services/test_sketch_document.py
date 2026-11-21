"""Definition-only sketch parsing and rendering."""

from __future__ import annotations

import unittest

from lazyplan.services.sketch_document import (
    SketchDocument,
    SketchDocumentError,
    parse_sketch,
    render_sketch,
)

CANONICAL = """# Sketch title

## Why

Because review should stay at the definition.

## What

## Scope

- One thing.

## Done

- The sketch round-trips.
- The parser refuses a missing title.
"""


class SketchDocumentTest(unittest.TestCase):
    def test_canonical_round_trip(self) -> None:
        document = parse_sketch(CANONICAL)
        self.assertEqual(document.title, "Sketch title")
        self.assertEqual(document.why, "Because review should stay at the definition.")
        self.assertEqual(document.what, "## Scope\n\n- One thing.")
        self.assertEqual(
            document.criteria,
            ("The sketch round-trips.", "The parser refuses a missing title."),
        )
        self.assertEqual(parse_sketch(render_sketch(document)), document)
        self.assertEqual(
            render_sketch(parse_sketch(render_sketch(document))), render_sketch(document)
        )

    def test_section_aliases(self) -> None:
        document = parse_sketch(
            "# T\n\n## Goal\n\nWhy.\n\n## Scope\n\nWhat.\n\n## Acceptance criteria\n\n- Works.\n"
        )
        self.assertEqual((document.why, document.what), ("Why.", "What."))
        self.assertEqual(document.criteria, ("Works.",))

    def test_unknown_sections_stay_in_what(self) -> None:
        document = parse_sketch(
            "# T\n\n## Why\n\nWhy.\n\n## What\n\nBase.\n\n## Risks\n\n- One risk.\n"
        )
        self.assertEqual(document.what, "Base.\n\n## Risks\n\n- One risk.")

    def test_checkboxes_and_paragraph_criteria(self) -> None:
        document = parse_sketch(
            "# T\n\n## Why\n\nWhy.\n\n## What\n\nWhat.\n\n"
            "## Done\n\n- [ ] First.\n- [x] Second.\n\nA paragraph criterion.\n"
        )
        self.assertEqual(
            document.criteria,
            ("First.", "Second.", "A paragraph criterion."),
        )

    def test_duplicate_criteria_are_collapsed(self) -> None:
        document = parse_sketch(
            "# T\n\n## Why\n\nWhy.\n\n## What\n\nWhat.\n\n## Done\n\n- Same.\n- Same.\n"
        )
        self.assertEqual(document.criteria, ("Same.",))

    def test_done_is_optional(self) -> None:
        document = parse_sketch("# T\n\n## Why\n\nWhy.\n\n## What\n\nWhat.\n")
        self.assertEqual(document.criteria, ())
        self.assertNotIn("## Done", render_sketch(document))

    def test_missing_title_is_refused(self) -> None:
        with self.assertRaisesRegex(SketchDocumentError, "# Title"):
            parse_sketch("## Why\n\nWhy.\n\n## What\n\nWhat.\n")

    def test_missing_sections_are_refused(self) -> None:
        with self.assertRaisesRegex(SketchDocumentError, "## Why"):
            parse_sketch("# T\n\n## What\n\nWhat.\n")
        with self.assertRaisesRegex(SketchDocumentError, "## What"):
            parse_sketch("# T\n\n## Why\n\nWhy.\n")

    def test_duplicate_known_sections_stay_as_prose(self) -> None:
        document = parse_sketch("# T\n\n## Why\n\nOne.\n\n## Why\n\nTwo.\n\n## What\n\nWhat.\n")
        self.assertEqual(document.why, "One.")
        self.assertEqual(document.what, "## Why\n\nTwo.\n\nWhat.")

    def test_windows_newlines_are_normalized(self) -> None:
        document = parse_sketch(CANONICAL.replace("\n", "\r\n"))
        self.assertEqual(
            document.criteria, ("The sketch round-trips.", "The parser refuses a missing title.")
        )

    def test_title_keeps_a_trailing_hash_in_the_name(self) -> None:
        document = parse_sketch("# Learn C#\n\n## Why\n\nWhy.\n\n## What\n\nWhat.\n")
        self.assertEqual(document.title, "Learn C#")

    def test_byte_order_mark_is_ignored(self) -> None:
        document = parse_sketch("\ufeff" + CANONICAL)
        self.assertEqual(document.title, "Sketch title")

    def test_document_requires_a_definition(self) -> None:
        with self.assertRaisesRegex(SketchDocumentError, "title"):
            SketchDocument(" ", "Why.", "What.")
        with self.assertRaisesRegex(SketchDocumentError, "why"):
            SketchDocument("T", " ", "What.")
        with self.assertRaisesRegex(SketchDocumentError, "what"):
            SketchDocument("T", "Why.", " ")
        with self.assertRaisesRegex(SketchDocumentError, "duplicate"):
            SketchDocument("T", "Why.", "What.", ("Same.", "Same."))


if __name__ == "__main__":
    unittest.main()
