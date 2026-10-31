"""Update cadence settings: defaults, env overrides, invalid values, clamping."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

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


class RefreshGateTest(unittest.TestCase):
    """One shared slot gates the network across every open instance."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name) / "home"

    def _claim(self, now: float, interval: float = 300.0) -> bool:
        return upgrade.claim_refresh(self.home, now=now, interval=interval)

    def _gate(self) -> Path:
        return upgrade.update_gate_path(self.home)

    def test_one_winner_per_interval(self) -> None:
        self.assertTrue(self._claim(1_000))
        self.assertFalse(self._claim(1_001))
        self.assertFalse(self._claim(1_299))
        self.assertTrue(self._claim(1_300))

    def test_backoff_is_honored_by_every_instance(self) -> None:
        self.assertTrue(self._claim(1_000))
        upgrade.defer_refresh(self.home, now=1_000, delay=900)
        self.assertFalse(self._claim(1_899))
        self.assertTrue(self._claim(1_900))

    def test_abandoned_partial_gate_is_stolen(self) -> None:
        gate = self._gate()
        gate.parent.mkdir(parents=True, exist_ok=True)
        gate.write_text("", encoding="utf-8")
        os.utime(gate, (800, 800))
        self.assertTrue(self._claim(1_000))

    def test_fresh_partial_gate_stays_locked(self) -> None:
        gate = self._gate()
        gate.parent.mkdir(parents=True, exist_ok=True)
        gate.write_text("", encoding="utf-8")
        os.utime(gate, (990, 990))
        self.assertFalse(self._claim(1_000))

    def test_gate_lives_in_the_shared_home(self) -> None:
        self.assertEqual(self._gate(), self.home / ".lazyplan" / upgrade.UPDATE_GATE_NAME)


if __name__ == "__main__":
    unittest.main()
