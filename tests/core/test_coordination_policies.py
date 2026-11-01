"""Pure coordination rules: TTL parsing, expiry, and block validation."""

from __future__ import annotations

import unittest

from lazyplan.core.entities import Claim, Status, Task
from lazyplan.core.policies.coordination import (
    CLAIM_DEFAULT_TTL,
    is_expired,
    parse_ttl,
    validate_block,
)


class TestTtl(unittest.TestCase):
    def test_default(self) -> None:
        self.assertEqual(parse_ttl(None), CLAIM_DEFAULT_TTL)

    def test_units(self) -> None:
        self.assertEqual(parse_ttl("30m"), 1800)
        self.assertEqual(parse_ttl("2.hours"), 7200)
        self.assertEqual(parse_ttl("90s"), 90)
        self.assertEqual(parse_ttl("1.days"), 86400)

    def test_invalid(self) -> None:
        with self.assertRaises(ValueError):
            parse_ttl("soon")
        with self.assertRaises(ValueError):
            parse_ttl("3.fortnights")


class TestExpiry(unittest.TestCase):
    def test_missing_claim_is_expired(self) -> None:
        self.assertTrue(is_expired(None, 100.0))

    def test_past_expiry(self) -> None:
        claim = Claim(task_id=1, actor="a", started_at=0.0, expires_at=100.0)
        self.assertTrue(is_expired(claim, 100.0))

    def test_active(self) -> None:
        claim = Claim(task_id=1, actor="a", started_at=0.0, expires_at=100.0)
        self.assertFalse(is_expired(claim, 99.0))


class TestBlockValidation(unittest.TestCase):
    def test_done_task_cannot_block(self) -> None:
        task = Task(id=1, milestone_id=1, title="T", status=Status.DONE)
        with self.assertRaises(ValueError):
            validate_block(task, "waiting")

    def test_reason_is_required(self) -> None:
        task = Task(id=1, milestone_id=1, title="T")
        with self.assertRaises(ValueError):
            validate_block(task, "  ")

    def test_open_task_with_reason(self) -> None:
        task = Task(id=1, milestone_id=1, title="T")
        validate_block(task, "waiting")


if __name__ == "__main__":
    unittest.main()
