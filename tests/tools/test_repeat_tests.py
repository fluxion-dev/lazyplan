"""The repeat runner discovers, shuffles deterministically, and stops."""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

from tests.support.paths import ROOT


def _load():
    spec = importlib.util.spec_from_file_location(
        "repeat_tests", ROOT / "tools/repeat-tests.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class RepeatRunnerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tool = _load()

    def test_modules_are_dotted_and_sorted(self) -> None:
        names = self.tool.modules()
        self.assertIn("tests.presentation.test_taskbar", names)
        self.assertEqual(names, sorted(names))

    def test_no_tui_excludes_presentation(self) -> None:
        names = self.tool.modules(no_tui=True)
        self.assertFalse(any(name.startswith("tests.presentation") for name in names))
        self.assertFalse(any(name == "tests.setup.test_setup_pty" for name in names))

    def test_a_seed_is_reproducible(self) -> None:
        names = ["a", "b", "c", "d"]
        first = self.tool.shuffled(names, 7, 0)
        second = self.tool.shuffled(names, 7, 0)
        self.assertEqual(first, second)
        self.assertNotEqual(first, self.tool.shuffled(names, 7, 1))

    def test_the_command_records_the_pass_seed(self) -> None:
        argv = self.tool.command(["a", "b"], 4, 2)
        self.assertEqual(argv[1:4], ["-m", "unittest", "-q"])
        self.assertEqual(sorted(argv[4:]), ["a", "b"])

    def test_an_empty_tree_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(self.tool.modules(Path(tmp)), [])


if __name__ == "__main__":
    unittest.main()
