"""One temp directory and one store for a test case.

Most service tests need the same shape: an isolated home-free directory and a
fresh SQLite store. Subclass ``StoreCase`` instead of rebuilding that in every
``setUp``; ``temp_store`` adds a second store registered for cleanup.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from lazyplan.store import Store


class StoreCase(unittest.TestCase):
    """A case with ``self.tmp``, ``self.db``, and ``self.store``."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / "lazyplan.db")
        self.store = Store(self.db)


def temp_store(case: unittest.TestCase, name: str = "other.db") -> Store:
    """A second store in its own temp directory, cleaned up with *case*."""
    directory = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
    case.addCleanup(directory.cleanup)
    return Store(Path(directory.name) / name)
