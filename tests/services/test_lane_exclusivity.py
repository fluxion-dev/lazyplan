"""One doing task per lane: claims, next, direct moves, and overrides."""

from __future__ import annotations

import tempfile
import unittest

from lazyplan.core.entities import Status
from lazyplan.services import coordination, planning
from lazyplan.store import Store


class LaneExclusivityTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(f"{self.tmp.name}/lane.db")
        self.plan = self.store.add_plan(
            "Lanes", dispatch_mode="parallel", max_agents=2, worktree_required=False
        )
        self.lane = self.store.add_milestone(self.plan.id, "One")
        self.first = self.store.add_task(self.lane.id, "First", "Commit. Verify.")
        self.second = self.store.add_task(self.lane.id, "Second", "Commit. Verify.")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_a_second_claim_names_the_holder_and_lane(self) -> None:
        coordination.start_claim(self.store, self.first.id, "worker")
        with self.assertRaisesRegex(ValueError, "already has T1 doing by worker"):
            coordination.start_claim(self.store, self.second.id, "other")

    def test_force_with_a_reason_allows_a_second_doing_task(self) -> None:
        coordination.start_claim(self.store, self.first.id, "worker")
        result = coordination.start_claim(
            self.store,
            self.second.id,
            "other",
            force=True,
            reason="handoff while the first waits on CI",
        )
        self.assertEqual(result["task"]["id"], self.second.id)

    def test_direct_status_move_matches_the_claim_rule(self) -> None:
        coordination.start_claim(self.store, self.first.id, "worker")
        with self.assertRaisesRegex(ValueError, "already has T1 doing"):
            planning.set_status(self.store, "task", self.second.id, Status.DOING, actor="other")

    def test_next_can_be_limited_to_one_lane(self) -> None:
        other = self.store.add_milestone(self.plan.id, "Two")
        task = self.store.add_task(other.id, "Work", "Commit. Verify.")
        result = coordination.claim_next(
            self.store, "worker", plan_id=self.plan.id, lane_id=other.id
        )
        assert result is not None
        self.assertEqual(result["task"]["id"], task.id)

    def test_session_end_records_one_handoff_and_releases(self) -> None:
        from pathlib import Path

        work = Path(self.tmp.name) / "work"
        work.mkdir()
        self.store.claim_task(self.first.id, "worker", worktree=str(work), repo_path=str(work))
        self.store.set_status_raw("task", self.first.id, Status.DOING)

        self.assertEqual(coordination.record_lane_handoffs(self.store, str(work)), 1)
        notes = self.store.list_notes("task", self.first.id)
        self.assertTrue(notes[-1].text.startswith(f"Lane M{self.lane.id} handoff"))
        self.assertEqual(coordination.record_lane_handoffs(self.store, str(work)), 0)

        coordination.end_checkout_claims(self.store, str(work))
        self.assertEqual(self.store.get_task(self.first.id).status, Status.TODO)
        self.assertIsNone(self.store.get_claim(self.first.id))


if __name__ == "__main__":
    unittest.main()
