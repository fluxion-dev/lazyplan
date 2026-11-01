"""The concrete Store must satisfy every narrow service port."""

from __future__ import annotations

import os
import tempfile
import unittest

from lazyplan.core.ports.collaboration import CollaborationPort
from lazyplan.core.ports.coordination import CoordinationPort
from lazyplan.core.ports.planning import PlanningPort
from lazyplan.store import Store


def _accepts_planning(port: PlanningPort) -> None:
    """Compile-time structural check; runtime is a no-op."""
    assert port is not None


def _accepts_coordination(port: CoordinationPort) -> None:
    """Compile-time structural check; runtime is a no-op."""
    assert port is not None


def _accepts_collaboration(port: CollaborationPort) -> None:
    """Compile-time structural check; runtime is a no-op."""
    assert port is not None


class TestStorePorts(unittest.TestCase):
    def test_store_satisfies_planning_port(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(os.path.join(tmp, "ports.db"))
            _accepts_planning(store)

    def test_store_satisfies_coordination_port(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(os.path.join(tmp, "coordination.db"))
            _accepts_coordination(store)

    def test_store_satisfies_collaboration_port(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(os.path.join(tmp, "collaboration.db"))
            _accepts_collaboration(store)


if __name__ == "__main__":
    unittest.main()
