"""Release hygiene: pyproject.toml is the single source of truth for the
semantic version; the README header mirrors it (maintained by tools/bump.sh).
Runs inside the normal gate suite, so version drift fails the build."""

import os
import re
import sys
import tomllib
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

ROOT = Path(__file__).parent.parent
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


class TestVersion(unittest.TestCase):
    def test_pyproject_version_is_semver(self):
        with open(ROOT / "pyproject.toml", "rb") as fh:
            version = tomllib.load(fh)["project"]["version"]
        self.assertRegex(version, SEMVER)

    def test_readme_header_matches_pyproject(self):
        with open(ROOT / "pyproject.toml", "rb") as fh:
            version = tomllib.load(fh)["project"]["version"]
        header = (ROOT / "README.md").read_text().splitlines()[0]
        self.assertEqual(header, f"# lazyplan (`lpui`) — v{version}")


if __name__ == "__main__":
    unittest.main()
