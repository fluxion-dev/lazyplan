"""Release hygiene: pyproject.toml is the single source of truth for the
semantic version; the README header mirrors it (maintained by tools/bump.sh).
Runs inside the normal gate suite, so version drift fails the build."""

import os
import re
import sys
import tempfile
import tomllib
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from lazyplan.cli import main  # noqa: E402
from lazyplan.cli_parser import package_version  # noqa: E402

ROOT = Path(__file__).parent.parent
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


class TestVersion(unittest.TestCase):
    def _version(self) -> str:
        with open(ROOT / "pyproject.toml", "rb") as fh:
            return tomllib.load(fh)["project"]["version"]

    def test_pyproject_version_is_semver(self):
        self.assertRegex(self._version(), SEMVER)

    def test_readme_header_matches_pyproject(self):
        version = self._version()
        header = (ROOT / "README.md").read_text(encoding="utf-8").splitlines()[0]
        self.assertEqual(header, f"# lazyplan (`lpui`) — v{version}")

    def test_site_version_matches_pyproject(self):
        import json

        version = self._version()
        html = (ROOT / "site/index.html").read_text(encoding="utf-8")
        self.assertIn(f'"version": "{version}"', html)
        self.assertIn(f"/releases/download/v{version}/", html)
        self.assertIn(f"img.shields.io/pypi/v/lazyplan-tui?v={version}", html)
        self.assertIn(f"img.shields.io/github/v/release/fluxion-dev/lazyplan?v={version}", html)
        package = json.loads((ROOT / "site/package.json").read_text(encoding="utf-8"))
        self.assertEqual(package["version"], version)


class TestVersionFlag(unittest.TestCase):
    def _run(self, argv: list[str]) -> tuple[int, str]:
        buf = StringIO()
        with redirect_stdout(buf):
            code = main(argv)
        return code, buf.getvalue().strip()

    def test_version_prints_semver(self):
        code, out = self._run(["--version"])
        self.assertEqual(code, 0)
        self.assertEqual(out, package_version())
        self.assertRegex(out, SEMVER)

    def test_version_works_after_verb(self):
        code, out = self._run(["list", "--version"])
        self.assertEqual(code, 0)
        self.assertEqual(out, package_version())

    def test_version_creates_no_db(self):
        cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                code, _ = self._run(["--version"])
            finally:
                os.chdir(cwd)
            self.assertEqual(code, 0)
            self.assertFalse((Path(tmp) / ".agents/plan").exists())


if __name__ == "__main__":
    unittest.main()
