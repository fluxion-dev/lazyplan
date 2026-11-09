"""Removed override-mode symbols must not return to the source tree."""

from __future__ import annotations

import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "lazyplan"
FORBIDDEN = ("tui.override", "services.overrides", "WRITE_ACTIONS", "require_override")


class RemovedFeatureTest(unittest.TestCase):
    def test_override_mode_symbols_are_gone(self) -> None:
        hits: list[str] = []
        for path in sorted(SRC.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            text = path.read_text(encoding="utf-8")
            for name in FORBIDDEN:
                if name in text:
                    hits.append(f"{path.relative_to(SRC)}: {name}")
        self.assertEqual(hits, [], f"remove override-mode leftovers: {hits}")
