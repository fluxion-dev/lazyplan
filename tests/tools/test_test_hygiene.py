"""The hygiene scan finds leaked state and sleeps, and honors allowlists."""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

from tests.support.paths import ROOT


def _load():
    spec = importlib.util.spec_from_file_location("test_hygiene", ROOT / "tools/test_hygiene.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class HygieneTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tool = _load()
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "tests" / "support").mkdir(parents=True)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def write(self, relative: str, text: str) -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def test_a_real_home_lookup_is_a_finding(self) -> None:
        self.write("tests/test_bad.py", "home = Path." + "home()\n")
        findings = self.tool.scan(self.root)
        self.assertTrue(any("real home" in finding for finding in findings))

    def test_a_sleep_is_a_finding(self) -> None:
        self.write("tests/test_bad.py", "time." + "sleep(1)\n")
        findings = self.tool.scan(self.root)
        self.assertTrue(any("synchronization" in finding for finding in findings))

    def test_the_support_helper_is_exempt(self) -> None:
        self.write("tests/support/home.py", "home = Path." + "home()\n")
        self.assertEqual(self.tool.scan(self.root), [])

    def test_an_allowlisted_file_is_exempt_for_home_only(self) -> None:
        name = "tests/vcs/test_repo.py"
        self.write(name, "home = Path." + "home()\n")
        self.tool.HOME_ALLOWLIST[name] = "read-only path assertion"
        try:
            self.assertEqual(self.tool.scan(self.root), [])
        finally:
            self.tool.HOME_ALLOWLIST.pop(name, None)
