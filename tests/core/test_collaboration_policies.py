"""Pure collaboration rules: note/comment validation and mentions."""

from __future__ import annotations

import unittest

from lazyplan.core.policies.collaboration import (
    mention_needle,
    validate_comment,
    validate_note,
)


class TestValidation(unittest.TestCase):
    def test_notes_are_trimmed(self) -> None:
        self.assertEqual(validate_note("  handoff  "), "handoff")

    def test_empty_note_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            validate_note("   ")

    def test_empty_comment_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            validate_comment("")

    def test_comment_is_trimmed(self) -> None:
        self.assertEqual(validate_comment(" reviewed "), "reviewed")


class TestMentions(unittest.TestCase):
    def test_name_is_normalized(self) -> None:
        self.assertEqual(mention_needle("Alice"), "@alice")
        self.assertEqual(mention_needle("@alice"), "@alice")

    def test_empty_name_is_safe(self) -> None:
        self.assertEqual(mention_needle(None), "@")


if __name__ == "__main__":
    unittest.main()
