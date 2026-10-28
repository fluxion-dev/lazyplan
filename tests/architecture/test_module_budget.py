"""Keep hand-written source modules inside the agreed line budget."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "lazyplan"
BASELINE = Path(__file__).with_name("architecture_baseline.json")
DEFAULT_BUDGET = 600


def source_files() -> list[Path]:
    """Return every hand-written Python module under ``src/lazyplan``."""
    return sorted(path for path in SRC.rglob("*.py") if "__pycache__" not in path.parts)


def budgets() -> dict[str, int]:
    """Return the recorded per-file budgets."""
    data = json.loads(BASELINE.read_text(encoding="utf-8"))
    return {name: int(limit) for name, limit in data["budgets"].items()}


def over_budget(
    files: list[Path],
    recorded: dict[str, int],
    root: Path = SRC,
) -> list[str]:
    """Return one message per *file* that exceeds its budget."""
    failures: list[str] = []
    for path in files:
        relative = path.relative_to(root).as_posix()
        limit = recorded.get(relative, DEFAULT_BUDGET)
        lines = len(path.read_text(encoding="utf-8").splitlines())
        if lines > limit:
            failures.append(f"{relative}: {lines} lines, budget {limit}")
    return failures


class ModuleBudgetTest(unittest.TestCase):
    """A file may only exceed the default budget while a split is planned."""

    def test_every_module_is_under_budget(self) -> None:
        failures = over_budget(source_files(), budgets())
        self.assertEqual(
            failures,
            [],
            "split these modules or record the new budget: " + "; ".join(failures),
        )

    def test_over_budget_reports_growth(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "big.py"
            path.write_text(
                "\n".join("x = 1" for _ in range(DEFAULT_BUDGET + 1)),
                encoding="utf-8",
            )
            failures = over_budget([path], {}, root=root)
        self.assertEqual(failures, [f"big.py: {DEFAULT_BUDGET + 1} lines, budget {DEFAULT_BUDGET}"])

    def testrecord_findinged_budgets_match_existing_files(self) -> None:
        files = {path.relative_to(SRC).as_posix() for path in source_files()}
        stale = sorted(set(budgets()) - files)
        self.assertEqual(stale, [], f"remove stale budget entries: {stale}")


if __name__ == "__main__":
    unittest.main()
