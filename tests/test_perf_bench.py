"""The performance benchmark fixture is deterministic, offline, and isolated."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from lazyplan.store import Store  # noqa: E402


def _load():
    spec = importlib.util.spec_from_file_location("perf_bench", ROOT / "tools" / "perf_bench.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class PerfBenchCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bench = _load()

    def _fixture(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return self.bench.build_fixture(Path(tmp.name) / "perf.db", self.bench.QUICK_COUNTS)

    def test_fixture_counts_are_exact(self):
        fixture = self._fixture()
        expected = {
            "plans": self.bench.QUICK_COUNTS.plans,
            "milestones": self.bench.QUICK_COUNTS.milestones,
            "tasks": self.bench.QUICK_COUNTS.tasks,
            "criteria": self.bench.QUICK_COUNTS.criteria,
            "events": self.bench.QUICK_COUNTS.events,
            "vcs_links": self.bench.QUICK_COUNTS.links,
            "entity_repos": self.bench.QUICK_COUNTS.repos,
        }
        self.assertEqual(fixture.counts, expected)

    def test_fixture_is_deterministic(self):
        def signature(fixture):
            store = Store(fixture.db)
            base = str(fixture.db.parent)
            plans = store.list_plans()
            milestones = [m for plan in plans for m in store.list_milestones(plan.id)]
            tasks = [t for milestone in milestones for t in store.list_tasks(milestone.id)]
            events = store.feed(limit=1_000_000)
            return (
                tuple((plan.id, plan.name, plan.status.value) for plan in plans),
                tuple((item.id, item.plan_id, item.title) for item in milestones),
                tuple((item.id, item.milestone_id, item.title) for item in tasks),
                tuple(
                    (
                        row["ts"],
                        row["actor"],
                        row["kind"],
                        row["action"],
                        row["detail"].replace(base, "<tmp>"),
                    )
                    for row in events
                ),
            )

        first = signature(self._fixture())
        second = signature(self._fixture())
        self.assertEqual(first, second)

    def test_report_measures_core_paths_without_network(self):
        with mock.patch("urllib.request.urlopen", side_effect=AssertionError("network")):
            result = self.bench.run(
                self.bench.QUICK_COUNTS,
                repeat=1,
                include_tui=False,
            )
        names = {metric["name"] for metric in result["metrics"]}
        for name in (
            "services.tree",
            "services.tree_limit5",
            "attention_ids",
            "list_text",
            "list_json",
            "show_plan",
            "export_all",
            "audit_report",
            "git_status",
            "git_show",
            "tui_refresh",
        ):
            self.assertIn(name, names)
        tree = next(metric for metric in result["metrics"] if metric["name"] == "services.tree")
        self.assertIsNotNone(tree["ms"])
        self.assertGreater(tree["queries"] or 0, 0)
        tui = next(metric for metric in result["metrics"] if metric["name"] == "tui_refresh")
        self.assertEqual(tui["note"], "disabled by --no-tui")

    def test_tui_refresh_is_measured_when_textual_is_available(self):
        if importlib.util.find_spec("textual") is None:
            self.skipTest("textual not installed")
        result = self.bench.run(self.bench.QUICK_COUNTS, repeat=1, include_tui=True)
        tui = next(metric for metric in result["metrics"] if metric["name"] == "tui_refresh")
        self.assertIsNotNone(tui["ms"])
        self.assertGreater(tui["queries"] or 0, 0)

    def test_benchmark_leaves_the_real_home_alone(self):
        home = Path.home()
        before = set(home.glob(".lazyplan/*")) if (home / ".lazyplan").is_dir() else set()
        self.bench.run(self.bench.QUICK_COUNTS, repeat=1, include_tui=False)
        after = set(home.glob(".lazyplan/*")) if (home / ".lazyplan").is_dir() else set()
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
