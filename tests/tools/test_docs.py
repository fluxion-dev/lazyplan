"""The docs gate rejects stray prose and broken links on tiny fixtures."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.support.paths import ROOT


def _load():
    spec = importlib.util.spec_from_file_location("check_docs", ROOT / "tools" / "check-docs.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class DocsGateCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gate = _load()
        cls.legacy = cls.gate.LEGACY_DOCS

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        for name in ("README.md", "CONTRIBUTING.md", "CHANGELOG.md", "AGENTS.md"):
            (self.root / name).write_text(f"# {name}\n\nDo not restate source.\n", encoding="utf-8")
        (self.root / "docs").mkdir()
        (self.root / "docs/usage.md").write_text("# usage\n", encoding="utf-8")
        patcher = mock.patch.object(self.gate, "LEGACY_DOCS", frozenset())
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_clean_fixture_passes(self):
        self.assertEqual(self.gate.check(self.root), [])

    def test_unapproved_markdown_fails(self):
        (self.root / "docs/extra.md").write_text("# extra\n", encoding="utf-8")
        self.assertIn("unapproved Markdown: docs/extra.md", self.gate.check(self.root))

    def test_skipped_directories_are_ignored(self):
        for name in ("tests/fixtures", "src/lazyplan/data", ".agents/skills"):
            directory = self.root / name
            directory.mkdir(parents=True)
            (directory / "README.md").write_text("# generated\n", encoding="utf-8")
        self.assertEqual(self.gate.check(self.root), [])

    def test_broken_relative_link_fails(self):
        (self.root / "CONTRIBUTING.md").write_text("[gone](docs/missing.md)\n", encoding="utf-8")
        errors = self.gate.check(self.root)
        self.assertTrue(any("broken relative link" in error for error in errors), errors)

    def test_external_links_are_exempt(self):
        (self.root / "README.md").write_text(
            "[site](https://example.com/x) [mail](mailto:a@b.c) [top](#top)\n",
            encoding="utf-8",
        )
        self.assertEqual(self.gate.check(self.root), [])

    def test_links_in_code_are_ignored(self):
        (self.root / "README.md").write_text(
            "`[x](missing.md)`\n\n```\n[y](missing.md)\n```\n", encoding="utf-8"
        )
        self.assertEqual(self.gate.check(self.root), [])

    def test_missing_policy_sentence_fails(self):
        (self.root / "AGENTS.md").write_text("# agents\n", encoding="utf-8")
        errors = self.gate.check(self.root)
        self.assertTrue(any("documentation policy" in error for error in errors), errors)

    def test_stale_legacy_entry_fails(self):
        with mock.patch.object(self.gate, "LEGACY_DOCS", frozenset({"docs/gone.md"})):
            errors = self.gate.check(self.root)
        self.assertTrue(any("remove it from LEGACY_DOCS" in error for error in errors), errors)

    def test_real_repo_passes(self):
        with mock.patch.object(self.gate, "LEGACY_DOCS", self.legacy):
            self.assertEqual(self.gate.check(ROOT), [])

    def test_check_script_runs_the_gate(self):
        script = (ROOT / "tools/check.sh").read_text(encoding="utf-8")
        self.assertIn("tools/check-docs.py", script)


if __name__ == "__main__":
    unittest.main()
