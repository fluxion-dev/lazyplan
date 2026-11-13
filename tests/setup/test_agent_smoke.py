"""The live-host smoke proves exact identity and the lost sweep."""

from __future__ import annotations

import subprocess
import sys
import unittest

from tests.support.paths import ROOT


class AgentSmokeTest(unittest.TestCase):
    def test_live_host_is_exact_then_lost(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "agent-smoke.py")],
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("exact identity, then lost", result.stdout)


if __name__ == "__main__":
    unittest.main()
