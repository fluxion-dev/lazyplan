"""The IA inventory covers every surface and fails on drift."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest

from tests.support.paths import ROOT
from tests.support.tools import load_tool


class TestIaInventory(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tool = load_tool("ia_inventory")

    def test_report_covers_every_surface(self):
        report = self.tool.build_report()
        self.assertGreater(report["counts"]["cli_commands"], 0)
        self.assertGreater(report["counts"]["palette_commands"], 0)
        self.assertGreater(report["counts"]["mcp_tools"], 0)
        self.assertGreater(report["counts"]["mcp_resources"], 0)
        self.assertGreater(report["counts"]["tui_screens"], 0)
        self.assertGreater(report["counts"]["tui_bindings"], 0)
        self.assertGreater(report["counts"]["setup_steps"], 0)
        self.assertGreater(report["counts"]["hook_events"], 0)
        self.assertGreater(report["counts"]["doc_files"], 0)

    def test_committed_snapshot_is_current(self):
        self.assertEqual(self.tool.main(["--check"]), 0)

    def test_drift_names_the_stale_snapshot(self):
        report = self.tool.build_report()
        report["cli"]["commands"].pop()
        errors = self.tool.compare(report)
        self.assertTrue(any("stale snapshot" in error for error in errors), errors)

    def test_stdlib_only_without_site_packages(self):
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        result = subprocess.run(
            [sys.executable, "-S", "tools/ia_inventory.py", "--json"],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIsInstance(json.loads(result.stdout), dict)


if __name__ == "__main__":
    unittest.main()
