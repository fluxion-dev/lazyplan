"""Heal mode: off reports drift and leaves parents alone."""

from __future__ import annotations

import os
import tempfile
import unittest

from lazyplan import services
from lazyplan.core.entities import Status
from lazyplan.store import Store


class TestHealMode(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(os.path.join(self.tmp.name, "heal.db"))
        self.plan = self.store.add_plan("P", actor="fixture")
        self.milestone = self.store.add_milestone(self.plan.id, "M", actor="fixture")
        self.task = self.store.add_task(self.milestone.id, "T", actor="fixture")

    def tearDown(self):
        self.tmp.cleanup()

    def test_no_heal_leaves_parents_alone(self):
        services.set_status(self.store, "task", self.task.id, Status.DOING, actor="fixture")
        services.set_status(
            self.store, "task", self.task.id, Status.DONE, actor="fixture", heal=False
        )
        self.assertEqual(self.store.get_milestone(self.milestone.id).status, Status.DOING)
        self.assertEqual(self.store.get_plan(self.plan.id).status, Status.DOING)
        services.set_status(self.store, "task", self.task.id, Status.DOING, actor="fixture")
        services.set_status(self.store, "task", self.task.id, Status.DONE, actor="fixture")
        self.assertEqual(self.store.get_milestone(self.milestone.id).status, Status.DONE)
        self.assertEqual(self.store.get_plan(self.plan.id).status, Status.DONE)

    def test_reconcile_without_heal_reports_only(self):
        services.set_status(self.store, "task", self.task.id, Status.DONE, actor="fixture")
        self.store.set_status_raw("milestone", self.milestone.id, Status.DOING)
        report = services.reconcile(self.store, actor="fixture", heal_mode=False)
        self.assertTrue(report["changes"])
        self.assertEqual(self.store.get_milestone(self.milestone.id).status, Status.DOING)
