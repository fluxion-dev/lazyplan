"""The changelog gate rejects undated headings and stamps the next release."""

from __future__ import annotations

import io
import re
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from tests.support.paths import ROOT
from tests.support.tools import load_tool

VALID = """# Changelog

## Unreleased

### Fixed

- Pending fix.

## v0.41.0 — 2026-11-12

### Changed

- Shipped change.
"""


class ChangelogGateCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gate = load_tool("check-changelog")

    def test_valid_changelog_passes(self):
        self.assertEqual(self.gate.check_text(VALID), [])

    def test_released_version_without_a_date_fails(self):
        errors = self.gate.check_text(VALID.replace("2026-11-12", "unreleased"))
        self.assertTrue(any("invalid release heading" in error for error in errors), errors)

    def test_missing_date_fails(self):
        text = VALID.replace("## v0.41.0 — 2026-11-12", "## v0.41.0")
        errors = self.gate.check_text(text)
        self.assertTrue(any("invalid release heading" in error for error in errors), errors)

    def test_duplicate_version_fails(self):
        text = VALID + "\n## v0.41.0 — 2026-11-11\n\n### Fixed\n\n- Again.\n"
        errors = self.gate.check_text(text)
        self.assertTrue(any("duplicate release version" in error for error in errors), errors)

    def test_out_of_order_version_fails(self):
        text = """# Changelog

## v0.40.0 — 2026-11-10

### Fixed

- Older.

## v0.41.0 — 2026-11-12

### Fixed

- Newer.
"""
        errors = self.gate.check_text(text)
        self.assertTrue(any("out of order" in error for error in errors), errors)

    def test_empty_unreleased_section_fails(self):
        text = """# Changelog

## Unreleased

## v0.41.0 — 2026-11-12

### Fixed

- Shipped.
"""
        errors = self.gate.check_text(text)
        self.assertTrue(any("section is empty" in error for error in errors), errors)

    def test_unreleased_without_a_section_heading_fails(self):
        text = VALID.replace("### Fixed\n\n- Pending fix.\n", "- Pending fix.\n")
        errors = self.gate.check_text(text)
        self.assertTrue(
            any("needs an Added, Changed, or Fixed heading" in error for error in errors), errors
        )

    def test_unreleased_must_be_first(self):
        text = VALID.replace(
            "## Unreleased\n\n### Fixed\n\n- Pending fix.\n\n",
            "",
        ).replace(
            "# Changelog\n\n",
            "# Changelog\n\n## v0.40.0 — 2026-11-11\n\n### Fixed\n\n- Older.\n\n"
            "## Unreleased\n\n### Fixed\n\n- Pending fix.\n\n",
        )
        errors = self.gate.check_text(text)
        self.assertTrue(
            any("must be the first release heading" in error for error in errors), errors
        )

    def test_unreleased_section_is_optional(self):
        text = VALID.replace("## Unreleased\n\n### Fixed\n\n- Pending fix.\n\n", "")
        self.assertEqual(self.gate.check_text(text), [])

    def test_earlier_releases_follows_versioned_sections(self):
        text = VALID + "\n## Earlier releases\n\nSee the releases page.\n"
        self.assertEqual(self.gate.check_text(text), [])

    def test_earlier_releases_before_a_version_fails(self):
        text = """# Changelog

## Earlier releases

See the releases page.

## v0.41.0 — 2026-11-12

### Fixed

- Shipped.
"""
        errors = self.gate.check_text(text)
        self.assertTrue(any("must follow a version heading" in error for error in errors), errors)

    def test_stamp_replaces_the_unreleased_heading(self):
        stamped = self.gate.stamp_text(VALID, "0.41.1", "2026-11-12")
        self.assertIn("## v0.41.1 — 2026-11-12", stamped)
        self.assertNotIn("## Unreleased", stamped)
        self.assertIn("- Pending fix.", stamped)

    def test_stamp_refuses_a_missing_unreleased_section(self):
        with self.assertRaisesRegex(ValueError, "has no ## Unreleased"):
            self.gate.stamp_text("# Changelog\n", "0.41.1", "2026-11-12")

    def test_stamp_refuses_an_empty_unreleased_section(self):
        text = (
            "# Changelog\n\n## Unreleased\n\n## v0.41.0 — 2026-11-12\n\n### Fixed\n\n- Shipped.\n"
        )
        with self.assertRaisesRegex(ValueError, "section is empty"):
            self.gate.stamp_text(text, "0.41.1", "2026-11-12")

    def test_stamp_refuses_a_non_version(self):
        with self.assertRaisesRegex(ValueError, "not a version"):
            self.gate.stamp_text(VALID, "next", "2026-11-12")

    def test_stamp_file_updates_both_copies(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "CHANGELOG.md"
            packaged = root / "src/lazyplan/data/CHANGELOG.md"
            source.write_text(VALID, encoding="utf-8")
            packaged.parent.mkdir(parents=True)
            packaged.write_text(VALID, encoding="utf-8")
            with (
                mock.patch.object(self.gate, "SOURCE", source),
                mock.patch.object(self.gate, "PACKAGED", packaged),
            ):
                day = self.gate.stamp_file("0.41.1", "2026-11-12")
            self.assertEqual(day, "2026-11-12")
            self.assertEqual(source.read_bytes(), packaged.read_bytes())
            self.assertIn("## v0.41.1 — 2026-11-12", source.read_text(encoding="utf-8"))

    def test_main_stamps_both_copies(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "CHANGELOG.md"
            packaged = root / "src/lazyplan/data/CHANGELOG.md"
            source.write_text(VALID, encoding="utf-8")
            packaged.parent.mkdir(parents=True)
            packaged.write_text(VALID, encoding="utf-8")
            out, err = io.StringIO(), io.StringIO()
            with (
                mock.patch.object(self.gate, "SOURCE", source),
                mock.patch.object(self.gate, "PACKAGED", packaged),
                redirect_stdout(out),
                redirect_stderr(err),
            ):
                code = self.gate.main(["--stamp", "0.41.1"])
            self.assertEqual(code, 0, err.getvalue())
            self.assertIn("stamped CHANGELOG.md as v0.41.1", out.getvalue())
            self.assertEqual(source.read_bytes(), packaged.read_bytes())

    def test_real_repo_passes(self):
        text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertEqual(self.gate.check_text(text), [])

    def test_real_repo_stamps_cleanly(self):
        text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        if "## Unreleased" not in text:
            self.skipTest("the released changelog has no Unreleased section")
        released = re.findall(r"^## v(\d+)\.(\d+)\.(\d+)", text, re.MULTILINE)
        self.assertTrue(released)
        major, minor, patch = (int(part) for part in released[0])
        version = f"{major}.{minor}.{patch + 1}"
        stamped = self.gate.stamp_text(text, version, "2026-11-12")
        self.assertEqual(self.gate.check_text(stamped), [])
        self.assertIn(f"## v{version} — 2026-11-12", stamped)
        self.assertIn(f"## v{major}.{minor}.{patch} — ", stamped)


if __name__ == "__main__":
    unittest.main()
