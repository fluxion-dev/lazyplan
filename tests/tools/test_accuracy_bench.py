"""The synthetic benchmark is deterministic and shows the improvement."""

import importlib.util
import unittest
from pathlib import Path

from tests.support.paths import ROOT


def _load():
    spec = importlib.util.spec_from_file_location(
        "accuracy_bench", ROOT / "tools" / "accuracy_bench.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class BenchCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bench = _load()

    def _metrics(self, row: dict) -> tuple:
        return (
            row["commits_total"],
            row["commits_linked"],
            round(row["coverage"], 3),
            round(row["median_lag_commits"], 2),
            len(row["criteria_gaps"]),
        )

    def test_two_runs_are_identical(self):
        first = self.bench.run()
        second = self.bench.run()
        self.assertEqual(self._metrics(first["baseline"]), self._metrics(second["baseline"]))
        self.assertEqual(
            self._metrics(first["intervention"]), self._metrics(second["intervention"])
        )

    def test_intervention_meets_the_targets(self):
        result = self.bench.run()
        intervention = result["intervention"]
        self.assertEqual(intervention["commits_total"], 8)
        self.assertEqual(intervention["coverage"], 1.0)
        self.assertLessEqual(intervention["median_lag_commits"], 1)
        self.assertEqual(intervention["criteria_gaps"], [])

    def test_baseline_is_worse_on_every_metric(self):
        result = self.bench.run()
        baseline = result["baseline"]
        intervention = result["intervention"]
        self.assertLess(baseline["coverage"], intervention["coverage"])
        self.assertGreaterEqual(baseline["median_lag_commits"], intervention["median_lag_commits"])
        self.assertGreater(len(baseline["criteria_gaps"]), len(intervention["criteria_gaps"]))

    def test_benchmark_leaves_the_real_home_alone(self):
        home = Path.home()
        before = set(home.glob(".lazyplan/*")) if (home / ".lazyplan").is_dir() else set()
        self.bench.run()
        after = set(home.glob(".lazyplan/*")) if (home / ".lazyplan").is_dir() else set()
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
