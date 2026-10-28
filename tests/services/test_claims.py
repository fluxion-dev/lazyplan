"""Task leases: one holder, expiry, renew, release, and export/import."""

from __future__ import annotations

import os
import tempfile
import unittest

from lazyplan import services
from lazyplan.models import Status
from lazyplan.store import ClaimConflict, ClaimMissing, Store


class TestClaims(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "claims.db")
        self.store = Store(self.db)
        plan = self.store.add_plan("P", actor="fixture")
        milestone = self.store.add_milestone(plan.id, "M", actor="fixture")
        self.task = self.store.add_task(milestone.id, "T", actor="fixture")

    def tearDown(self):
        self.tmp.cleanup()

    def test_claim_sets_actor_ttl_and_note(self):
        claim, previous = self.store.claim_task(
            self.task.id, "alice", ttl_seconds=60, note="taking it", now=1000
        )
        self.assertIsNone(previous)
        self.assertEqual(claim.actor, "alice")
        self.assertEqual(claim.started_at, 1000)
        self.assertEqual(claim.expires_at, 1060)
        self.assertEqual(claim.renewed_at, 1000)
        self.assertEqual(claim.note, "taking it")
        self.assertFalse(claim.expired(1059))
        self.assertTrue(claim.expired(1060))

    def test_second_actor_conflicts_until_expiry_or_force(self):
        self.store.claim_task(self.task.id, "alice", 60, now=1000)
        with self.assertRaises(ClaimConflict) as caught:
            self.store.claim_task(self.task.id, "bob", 60, now=1001)
        self.assertEqual(caught.exception.claim.actor, "alice")

        claim, previous = self.store.claim_task(self.task.id, "bob", 60, force=True, now=1002)
        self.assertEqual(claim.actor, "bob")
        assert previous is not None
        self.assertEqual(previous.actor, "alice")

    def test_expired_claim_is_reclaimable(self):
        self.store.claim_task(self.task.id, "alice", 10, now=1000)
        claim, previous = self.store.claim_task(self.task.id, "bob", 10, now=2000)
        self.assertEqual(claim.actor, "bob")
        assert previous is not None
        self.assertEqual(previous.actor, "alice")

    def test_renew_extends_only_the_holder(self):
        self.store.claim_task(self.task.id, "alice", 60, now=1000)
        renewed = self.store.renew_claim(self.task.id, "alice", 120, now=1010)
        self.assertEqual(renewed.started_at, 1000)
        self.assertEqual(renewed.renewed_at, 1010)
        self.assertEqual(renewed.expires_at, 1130)
        with self.assertRaises(ClaimConflict):
            self.store.renew_claim(self.task.id, "bob", 120, now=1011)
        with self.assertRaises(ClaimConflict):
            self.store.renew_claim(self.task.id, "alice", 120, now=2000)

    def test_renew_without_a_claim_is_missing(self):
        with self.assertRaises(ClaimMissing):
            self.store.renew_claim(self.task.id, "alice", 60, now=1000)

    def test_release_requires_the_holder_or_force(self):
        self.store.claim_task(self.task.id, "alice", 60, now=1000)
        with self.assertRaises(ClaimConflict):
            self.store.release_claim(self.task.id, "bob")
        released = self.store.release_claim(self.task.id, "bob", force=True)
        assert released is not None
        self.assertEqual(released.actor, "alice")
        self.assertIsNone(self.store.get_claim(self.task.id))
        self.assertIsNone(self.store.release_claim(self.task.id, "alice"))

    def test_list_claims_joins_context_and_filters(self):
        self.store.claim_task(self.task.id, "alice", 60, now=1000)
        active = self.store.list_claims(now=1001)
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["task_title"], "T")
        self.assertEqual(active[0]["plan_id"], 1)
        self.assertFalse(active[0]["expired"])
        self.assertEqual(self.store.list_claims(now=2000), [])
        expired = self.store.list_claims(include_expired=True, now=2000)
        self.assertEqual(len(expired), 1)
        self.assertTrue(expired[0]["expired"])
        self.assertEqual(self.store.list_claims(plan_id=1, now=1001)[0]["task_id"], self.task.id)
        self.assertEqual(self.store.list_claims(plan_id=99, now=1001), [])

    def test_deleting_a_task_removes_its_claim(self):
        self.store.claim_task(self.task.id, "alice", 60, now=1000)
        self.assertTrue(self.store.delete("task", self.task.id))
        self.assertIsNone(self.store.get_claim(self.task.id))

    def test_claim_rejects_done_tasks(self):
        services.set_status(self.store, "task", self.task.id, Status.DONE, actor="fixture")
        with self.assertRaises(ValueError):
            self.store.claim_task(self.task.id, "alice", 60, now=1000)

    def test_export_and_import_preserve_active_claims(self):
        self.store.claim_task(self.task.id, "alice", 600, note="handoff")
        data = services.export_all(self.store)
        claim = data["plans"][0]["milestones"][0]["tasks"][0]["claim"]
        self.assertEqual(claim["actor"], "alice")

        other = Store(os.path.join(self.tmp.name, "other.db"))
        counts = services.import_all(other, data, actor="fixture")
        self.assertEqual(counts["claims"], 1)
        imported = other.get_claim(1)
        assert imported is not None
        self.assertEqual(imported.actor, "alice")
        self.assertEqual(imported.note, "handoff")

    def test_export_import_skips_expired_claims(self):
        self.store.claim_task(self.task.id, "alice", 1, now=1)
        data = services.export_all(self.store)
        other = Store(os.path.join(self.tmp.name, "expired.db"))
        counts = services.import_all(other, data, actor="fixture")
        self.assertEqual(counts["claims"], 0)
        self.assertIsNone(other.get_claim(1))


if __name__ == "__main__":
    unittest.main()
