"""Doing and claimed are the same state for a task."""

from __future__ import annotations

import os
import tempfile
import unittest

from lazyplan import services
from lazyplan.core.entities import Status
from lazyplan.store import Store


class DoingClaimsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.store = Store(os.path.join(self.tmp.name, "doing.db"))
        plan = self.store.add_plan("P", actor="fixture", worktree_required=False)
        milestone = self.store.add_milestone(plan.id, "M", actor="fixture")
        self.task = self.store.add_task(milestone.id, "T", actor="fixture")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def move(self, status: Status, actor: str = "alice") -> None:
        services.set_status(self.store, "task", self.task.id, status, actor=actor)

    def test_moving_to_doing_claims_for_the_actor(self) -> None:
        self.move(Status.DOING)
        claim = self.store.get_claim(self.task.id)
        assert claim is not None
        self.assertEqual(claim.actor, "alice")
        self.assertEqual(claim.worktree, self.store.checkout_path())

    def test_leaving_doing_releases_the_claim(self) -> None:
        for status in (Status.DONE, Status.TODO):
            with self.subTest(status=status):
                self.move(Status.DOING)
                self.move(status)
                self.assertIsNone(self.store.get_claim(self.task.id))

    def test_another_actors_live_claim_refuses_doing(self) -> None:
        self.move(Status.DOING, actor="alice")
        self.move(Status.TODO, actor="alice")
        services.start_claim(self.store, self.task.id, "bob")
        with self.assertRaisesRegex(ValueError, "claimed by bob"):
            self.move(Status.DOING, actor="alice")
        claim = self.store.get_claim(self.task.id)
        assert claim is not None
        self.assertEqual(claim.actor, "bob")

    def test_the_holder_moving_to_doing_again_keeps_one_claim(self) -> None:
        services.start_claim(self.store, self.task.id, "alice")
        before = self.store.get_claim(self.task.id)
        self.move(Status.DOING, actor="alice")
        after = self.store.get_claim(self.task.id)
        assert before is not None and after is not None
        self.assertEqual(before.started_at, after.started_at)

    def test_an_expired_claim_does_not_block_doing(self) -> None:
        self.store.claim_task(self.task.id, "bob", ttl_seconds=1, now=0)
        self.move(Status.DOING, actor="alice")
        claim = self.store.get_claim(self.task.id)
        assert claim is not None
        self.assertEqual(claim.actor, "alice")


if __name__ == "__main__":
    unittest.main()
