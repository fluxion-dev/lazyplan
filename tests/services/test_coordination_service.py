"""Coordination use cases over the coordination port."""

from __future__ import annotations

import os
import tempfile
import unittest

from lazyplan import services
from lazyplan.core.errors import TouchpointOverlap
from lazyplan.core.policies.coordination import parse_ttl
from lazyplan.store import Store


class TestCoordinationService(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(os.path.join(self.tmp.name, "coord.db"))
        plan = self.store.add_plan("P", actor="fixture")
        milestone = self.store.add_milestone(plan.id, "M", actor="fixture")
        self.task = self.store.add_task(milestone.id, "T", actor="fixture")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_suggest_selects_without_claiming(self) -> None:
        result = services.claim_next(self.store, "alice", suggest=True)
        assert result is not None
        self.assertIsNone(result["claim"])
        self.assertEqual(result["task"]["id"], self.task.id)
        self.assertIsNone(self.store.get_claim(self.task.id))

    def test_claim_moves_the_task_doing(self) -> None:
        result = services.start_claim(self.store, self.task.id, "alice", ttl="10m")
        self.assertEqual(result["claim"]["actor"], "alice")
        self.assertEqual(self.store.get_task(self.task.id).status.value, "doing")
        self.assertEqual(parse_ttl("10m"), 600)

    def test_block_requires_a_reason(self) -> None:
        with self.assertRaises(ValueError):
            services.block_task(self.store, self.task.id, "  ")

    def _add_task(self, title: str, touch: str, repo: str = "") -> int:
        task = self.store.add_task(self.task.milestone_id, title, actor="fixture")
        self.store.add_touchpoint(task.id, touch)
        if repo:
            self.store.add_repo_link("task", task.id, repo, actor="fixture")
        return task.id

    def test_next_skips_overlapping_touchpoints(self) -> None:
        services.start_claim(self.store, self.task.id, "seed")
        first = self._add_task("Store", "src/store")
        self._add_task("Store file", "src/store/base.py")
        free = self._add_task("Tests", "tests")
        self.store.add_repo_link("task", first, "/repo", actor="fixture")
        services.start_claim(self.store, first, "alice", repo_path="/repo", worktree="/repo")
        result = services.claim_next(self.store, "bob")
        assert result is not None
        self.assertEqual(result["task"]["id"], free)

    def test_manual_claim_refuses_overlap_but_force_works(self) -> None:
        first = self._add_task("Store", "src/store")
        second = self._add_task("Store file", "src/store/base.py")
        self.store.add_repo_link("task", first, "/repo", actor="fixture")
        self.store.add_repo_link("task", second, "/repo", actor="fixture")
        services.start_claim(self.store, first, "alice", repo_path="/repo")
        with self.assertRaises(TouchpointOverlap):
            services.start_claim(self.store, second, "bob", repo_path="/repo")
        result = services.start_claim(self.store, second, "bob", repo_path="/repo", force=True)
        self.assertEqual(result["claim"]["actor"], "bob")

    def test_overlap_compares_normalized_repo_paths(self) -> None:
        first = self._add_task("Store", "src/store")
        second = self._add_task("Store file", "src/store/base.py")
        self.store.add_repo_link("task", first, "/repo", actor="fixture")
        self.store.add_repo_link("task", second, "/repo", actor="fixture")
        services.start_claim(self.store, first, "alice", repo_path="/repo/.")
        with self.assertRaises(TouchpointOverlap):
            services.start_claim(self.store, second, "bob", repo_path="/repo")

    def test_different_repos_do_not_overlap(self) -> None:
        first = self._add_task("A", "src/store", repo="/repo/a")
        second = self._add_task("B", "src/store", repo="/repo/b")
        services.start_claim(self.store, first, "alice", repo_path="/repo/a")
        result = services.start_claim(self.store, second, "bob", repo_path="/repo/b")
        self.assertEqual(result["task"]["id"], second)

    def test_task_without_touchpoints_is_never_blocked(self) -> None:
        services.start_claim(self.store, self.task.id, "seed")
        second = self._add_task("Free", "src/store")
        self.store.add_repo_link("task", second, "/repo", actor="fixture")
        result = services.claim_next(self.store, "bob")
        assert result is not None
        self.assertEqual(result["task"]["id"], second)


if __name__ == "__main__":
    unittest.main()
