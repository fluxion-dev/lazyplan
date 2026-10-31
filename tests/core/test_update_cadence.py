"""Update cadence settings: defaults, env overrides, invalid values, clamping."""

from __future__ import annotations

import unittest

from lazyplan import upgrade


class PollIntervalTest(unittest.TestCase):
    """The TUI poll interval is configurable but bounded."""

    def test_default_is_one_minute(self) -> None:
        self.assertEqual(upgrade.poll_interval({}), 60.0)

    def test_env_override(self) -> None:
        env = {upgrade.UPDATE_POLL_ENV: "15"}
        self.assertEqual(upgrade.poll_interval(env), 15.0)

    def test_invalid_values_fall_back(self) -> None:
        for raw in ("", "  ", "soon", "nan", "inf", "-inf"):
            with self.subTest(raw=raw):
                env = {upgrade.UPDATE_POLL_ENV: raw}
                self.assertEqual(upgrade.poll_interval(env), 60.0)

    def test_values_are_clamped(self) -> None:
        low = {upgrade.UPDATE_POLL_ENV: "0"}
        high = {upgrade.UPDATE_POLL_ENV: "999999"}
        self.assertEqual(upgrade.poll_interval(low), upgrade.UPDATE_MIN_POLL)
        self.assertEqual(upgrade.poll_interval(high), upgrade.UPDATE_MAX_POLL)


class NetworkIntervalTest(unittest.TestCase):
    """The shared network refresh is slower and separately configurable."""

    def test_default_is_five_minutes(self) -> None:
        self.assertEqual(upgrade.network_interval({}), 300.0)

    def test_env_override(self) -> None:
        env = {upgrade.UPDATE_NETWORK_ENV: "120"}
        self.assertEqual(upgrade.network_interval(env), 120.0)

    def test_invalid_values_fall_back(self) -> None:
        env = {upgrade.UPDATE_NETWORK_ENV: "often"}
        self.assertEqual(upgrade.network_interval(env), 300.0)

    def test_values_are_clamped(self) -> None:
        low = {upgrade.UPDATE_NETWORK_ENV: "1"}
        high = {upgrade.UPDATE_NETWORK_ENV: "999999"}
        self.assertEqual(upgrade.network_interval(low), upgrade.UPDATE_MIN_NETWORK)
        self.assertEqual(upgrade.network_interval(high), upgrade.UPDATE_MAX_NETWORK)

    def test_intervals_are_independent(self) -> None:
        env = {
            upgrade.UPDATE_POLL_ENV: "20",
            upgrade.UPDATE_NETWORK_ENV: "600",
        }
        self.assertEqual(upgrade.poll_interval(env), 20.0)
        self.assertEqual(upgrade.network_interval(env), 600.0)


if __name__ == "__main__":
    unittest.main()
