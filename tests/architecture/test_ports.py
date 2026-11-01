"""The concrete Store must satisfy every narrow service port."""

from __future__ import annotations

import os
import tempfile
import unittest

from lazyplan.core.ports.planning import PlanningPort
from lazyplan.store import Store


def _accepts_planning(port: PlanningPort) -> None:
    """Compile-time structural check; runtime is a no-op."""
    assert port is not None


class TestStorePorts(unittest.TestCase):
    def test_store_satisfies_planning_port(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(os.path.join(tmp, "ports.db"))
            _accepts_planning(store)


if __name__ == "__main__":
    unittest.main()
