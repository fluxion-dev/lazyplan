"""The navigation key table in the docs matches the registry."""

from __future__ import annotations

import unittest

from lazyplan.presentation.shared.help import KEYMAP
from tests.support.paths import ROOT

USAGE = (ROOT / "docs/usage.md").read_text(encoding="utf-8")
SITE = (ROOT / "site/index.html").read_text(encoding="utf-8")
SKILL = (ROOT / "src/lazyplan/data/SKILL.md").read_text(encoding="utf-8")


class DocumentationKeysTest(unittest.TestCase):
    def test_usage_lists_every_global_key(self) -> None:
        for key in ("?", "c", "q", "[", "]", "escape"):
            with self.subTest(key=key):
                self.assertIn(f"`{key}`", USAGE)

    def test_keymap_keys_appear_in_the_usage_guide(self) -> None:
        for key, _hint, _surface in KEYMAP:
            first = key.split(",")[0].split()[0]
            if "/" in first:
                continue
            with self.subTest(key=key):
                self.assertIn(first, USAGE)

    def test_docs_do_not_keep_the_old_key_meanings(self) -> None:
        self.assertNotIn("q` | add a question", USAGE)
        self.assertNotIn("`Q` | resolve", USAGE)

    def test_site_and_skill_name_the_shared_overlays(self) -> None:
        for name, text in (("site", SITE), ("skill", SKILL)):
            with self.subTest(surface=name):
                self.assertIn("palette", text.lower())
                self.assertIn("history", text.lower())

    def test_usage_names_every_trust_hub(self) -> None:
        for term in (
            "Trust hubs",
            "criteria hub",
            "evidence hub",
            "questions hub",
            "references hub",
        ):
            with self.subTest(term=term):
                self.assertIn(term, USAGE)
        for key in ("`t`", "`enter`", "`l`", "`L`", "`o`", "`d`"):
            with self.subTest(key=key):
                self.assertIn(key, USAGE)

    def test_site_and_skill_name_the_trust_hubs(self) -> None:
        for name, text in (("site", SITE), ("skill", SKILL)):
            with self.subTest(surface=name):
                self.assertIn("criteria", text.lower())
                self.assertIn("references", text.lower())

    def test_usage_names_every_coordination_hub(self) -> None:
        for term in (
            "Coordination hubs",
            "claims hub",
            "sessions hub",
            "comments and notes hub",
            "superseded",
        ):
            with self.subTest(term=term):
                self.assertIn(term, USAGE)

    def test_site_and_skill_name_the_coordination_hubs(self) -> None:
        for name, text in (("site", SITE), ("skill", SKILL)):
            with self.subTest(surface=name):
                self.assertIn("session", text.lower())
                self.assertIn("comment", text.lower())

    def test_usage_names_every_provenance_hub(self) -> None:
        for term in (
            "Provenance and activity hubs",
            "source trail",
            "pull request hub",
            "activity hub",
            "stale",
        ):
            with self.subTest(term=term):
                self.assertIn(term, USAGE)
        for key in ("`g`", "`enter`", "`r`", "`f`", "`K`"):
            with self.subTest(key=key):
                self.assertIn(key, USAGE)

    def test_site_and_skill_name_the_provenance_hubs(self) -> None:
        for name, text in (("site", SITE), ("skill", SKILL)):
            with self.subTest(surface=name):
                self.assertIn("pull request", text.lower())
                self.assertIn("activity", text.lower())
