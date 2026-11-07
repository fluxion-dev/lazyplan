"""One task snapshot gives the same done/total on every surface."""

from __future__ import annotations

import contextlib
import io
import os
import tempfile
import unittest

from lazyplan import services
from lazyplan.core.entities import Status
from lazyplan.core.policies.insights import progress as progress_snapshot
from lazyplan.presentation.cli import main as lpui_main
from lazyplan.presentation.tui.controllers.tree import TreeController
from lazyplan.store import Store


def _run(db: str, *argv: str) -> str:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = lpui_main(["--db", db, "--porcelain", *argv])
    if code != 0:
        raise AssertionError(f"{argv} exited {code}")
    return out.getvalue()


def _rows(text: str) -> dict[tuple[str, int], list[str]]:
    rows: dict[tuple[str, int], list[str]] = {}
    for line in text.splitlines():
        fields = line.split("\t")
        if len(fields) >= 6 and fields[0] in ("plan", "milestone"):
            rows[(fields[0], int(fields[1]))] = fields
    return rows


class TestProgressParity(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "parity.db")
        self.store = Store(self.db)
        self.plan = self.store.add_plan("P", actor="fixture")
        self.m1 = self.store.add_milestone(self.plan.id, "M1", actor="fixture")
        self.m2 = self.store.add_milestone(self.plan.id, "M2", actor="fixture")
        self.store.add_task(self.m1.id, "done", actor="fixture")
        self.store.add_task(self.m1.id, "doing", actor="fixture")
        self.store.add_task(self.m2.id, "todo", actor="fixture")
        self.store.add_task(self.m2.id, "todo2", actor="fixture")
        tasks = [
            task for milestone in (self.m1, self.m2) for task in self.store.list_tasks(milestone.id)
        ]
        services.set_status(self.store, "task", tasks[0].id, Status.DONE, actor="fixture")
        services.set_status(self.store, "task", tasks[1].id, Status.DOING, actor="fixture")

    def tearDown(self):
        self.tmp.cleanup()

    def test_every_surface_agrees(self):
        base = services.tree(self.store, status=None, archived="show")
        tui = TreeController.progress_map(base)
        milestones_by_plan = {self.plan.id: [row for row, _tasks in base[0][1]]}
        tasks_by_milestone = {row.id: tasks for row, tasks in base[0][1]}
        metrics = progress_snapshot(milestones_by_plan, tasks_by_milestone, [], 0.0)
        tasks = [task for tasks in tasks_by_milestone.values() for task in tasks]
        expected = f"{sum(1 for task in tasks if task.status == Status.DONE)}/{len(tasks)}"
        listed = _rows(_run(self.db, "list", "--tree"))
        shown = _rows(_run(self.db, "plan", "show", "--id", str(self.plan.id)))
        for rows in (listed, shown):
            self.assertEqual(rows[("plan", self.plan.id)][5], expected)
            self.assertEqual(rows[("milestone", self.m1.id)][5], "1/2")
            self.assertEqual(rows[("milestone", self.m2.id)][5], "0/2")
        self.assertEqual(tui[("plan", self.plan.id)][1], len(tasks))
        self.assertEqual(tui[("milestone", self.m1.id)], (1, 2))
        self.assertEqual(tui[("milestone", self.m2.id)], (0, 2))
        self.assertEqual((metrics.done, metrics.total), (1, len(tasks)))

    def test_filtered_list_keeps_full_progress(self):
        listed = _rows(_run(self.db, "list", "--tree", "--status", "doing"))
        self.assertEqual(listed[("plan", self.plan.id)][5], "1/4")

    def test_delete_and_import_keep_parents_consistent(self):
        for task in list(self.store.list_tasks(self.m1.id)):
            self.assertTrue(services.delete_row(self.store, "task", task.id, actor="fixture"))
        self.assertEqual(self.store.get_milestone(self.m1.id).status, Status.TODO)
        dump = services.export_all(self.store)
        dump["plans"][0]["milestones"][1]["status"] = "done"
        with tempfile.TemporaryDirectory() as other:
            target = Store(os.path.join(other, "target.db"))
            services.import_all(target, dump, actor="fixture")
            restored = target.list_milestones(target.list_plans()[0].id)[1]
            self.assertEqual(restored.status, Status.TODO)
