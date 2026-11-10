"""The environment facade exposes upgrade and staged-update helpers."""

from __future__ import annotations

import unittest

from lazyplan.infrastructure import environment


class TestEnvironmentFacade(unittest.TestCase):
    def test_version_helpers(self) -> None:
        self.assertEqual(environment.parse_version("v0.30.2"), (0, 30, 2))
        self.assertEqual(environment.poll_interval({}), 60.0)

    def test_stage_helpers(self) -> None:
        self.assertTrue(callable(environment.stage_update))
        self.assertTrue(callable(environment.apply_on_launch))


if __name__ == "__main__":
    unittest.main()
