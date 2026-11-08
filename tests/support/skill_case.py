"""Temporary repo and home pair shared by skill-install tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path


class SkillHomeCase(unittest.TestCase):
    """Create ``tmp/proj`` and ``tmp/home`` for one test."""

    repo_has_git = False

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name) / "proj"
        self.repo.mkdir()
        if self.repo_has_git:
            (self.repo / ".git").mkdir()
        self.home = Path(self.tmp.name) / "home"
        self.home.mkdir()
