"""Release notes: parsing, ranges, the seen marker, and the CLI surfaces."""

from __future__ import annotations

import importlib.util
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from lazyplan.presentation.cli import main
from lazyplan.presentation.cli.commands import admin
from lazyplan.presentation.cli.commands import system as system_cli
from lazyplan.services import notes
from tests.support.home import sandbox_home
from tests.support.paths import ROOT

SAMPLE = """# Changelog

## Unreleased

- Nothing yet.

## v0.38.0 — 2026-11-11

### Added

- New release notes.
- A second bullet.

## v0.37.0 — 2026-11-10

### Changed

- Mid release.

## v0.36.0 — 2026-11-09

### Fixed

- Old release.
"""


def run_main(argv: list[str]) -> tuple[int, str, str]:
    """Run the CLI and capture stdout and stderr."""
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main(argv)
    return code, out.getvalue(), err.getvalue()


class TestParse(unittest.TestCase):
    def test_versions_dates_and_bodies(self) -> None:
        releases = notes.parse(SAMPLE)
        self.assertEqual([release.version for release in releases], ["0.38.0", "0.37.0", "0.36.0"])
        self.assertEqual(releases[0].date, "2026-11-11")
        self.assertIn("New release notes.", releases[0].body)
        self.assertNotIn("Mid release", releases[0].body)

    def test_range_is_oldest_first_and_includes_both_ends(self) -> None:
        chosen = notes.select(notes.parse(SAMPLE), "0.38.0", since="0.36.0")
        self.assertEqual([release.version for release in chosen], ["0.37.0", "0.38.0"])

    def test_all_is_newest_first(self) -> None:
        chosen = notes.select(notes.parse(SAMPLE), "0.38.0", all_=True)
        self.assertEqual([release.version for release in chosen], ["0.38.0", "0.37.0", "0.36.0"])

    def test_missing_version_returns_no_notes(self) -> None:
        chosen, text = notes.select_notes("9.9.9", text=SAMPLE)
        self.assertEqual(chosen, ())
        self.assertEqual(text, "")

    def test_has_release_ignores_unreleased_headings(self) -> None:
        self.assertTrue(notes.has_release("0.37.0", text=SAMPLE))
        self.assertFalse(notes.has_release("Unreleased", text=SAMPLE))


class TestMarker(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        sandbox_home(self, self.home)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_first_install_records_and_stays_quiet(self) -> None:
        chosen, text = notes.advance_notice("0.38.0", text=SAMPLE)
        self.assertEqual((chosen, text), ((), ""))
        self.assertEqual(notes.read_seen(), "0.38.0")

    def test_upgrade_shows_every_skipped_version_once(self) -> None:
        notes.write_seen("0.36.0")
        chosen, text = notes.advance_notice("0.38.0", text=SAMPLE)
        self.assertEqual([release.version for release in chosen], ["0.37.0", "0.38.0"])
        self.assertLess(text.index("0.37.0"), text.index("0.38.0"))
        self.assertEqual(notes.read_seen(), "0.38.0")
        _again, second = notes.advance_notice("0.38.0", text=SAMPLE)
        self.assertEqual(second, "")

    def test_downgrade_records_the_installed_version_and_stays_quiet(self) -> None:
        notes.write_seen("0.38.0")
        chosen, text = notes.advance_notice("0.37.0", text=SAMPLE)
        self.assertEqual((chosen, text), ((), ""))
        self.assertEqual(notes.read_seen(), "0.37.0")

    def test_corrupt_marker_is_a_first_install(self) -> None:
        notes.marker_path().parent.mkdir(parents=True, exist_ok=True)
        notes.marker_path().write_text("{not json", encoding="utf-8")
        chosen, text = notes.advance_notice("0.38.0", text=SAMPLE)
        self.assertEqual((chosen, text), ((), ""))
        self.assertEqual(notes.read_seen(), "0.38.0")

    def test_seed_upgrade_only_fills_a_missing_marker(self) -> None:
        notes.seed_upgrade("0.37.0")
        self.assertEqual(notes.read_seen(), "0.37.0")
        notes.seed_upgrade("0.36.0")
        self.assertEqual(notes.read_seen(), "0.37.0")


class TestNotesCli(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        sandbox_home(self, self.tmp.name)
        self.env = mock.patch.dict(os.environ, {"LAZYPLAN_NO_SETUP": "1"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.bundled = mock.patch.object(notes, "bundled_text", return_value=SAMPLE)
        self.bundled.start()
        self.addCleanup(self.bundled.stop)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_default_prints_only_the_installed_version(self) -> None:
        code, out, err = run_main(["notes"])
        self.assertEqual(code, 0)
        self.assertEqual(err, "")
        self.assertIn("## v0.37.0", out)
        self.assertNotIn("## v0.38.0", out)
        self.assertNotIn("## v0.36.0", out)

    def test_all_prints_newest_first(self) -> None:
        code, out, _err = run_main(["notes", "--all"])
        self.assertEqual(code, 0)
        self.assertLess(out.index("## v0.38.0"), out.index("## v0.37.0"))
        self.assertLess(out.index("## v0.37.0"), out.index("## v0.36.0"))

    def test_since_prints_the_range_oldest_first(self) -> None:
        with mock.patch.object(system_cli, "package_version", return_value="0.38.0"):
            code, out, _err = run_main(["notes", "--since", "0.36.0"])
        self.assertEqual(code, 0)
        self.assertLess(out.index("## v0.37.0"), out.index("## v0.38.0"))
        self.assertNotIn("## v0.36.0", out)

    def test_json_carries_versions_dates_and_bodies(self) -> None:
        with mock.patch.object(system_cli, "package_version", return_value="0.38.0"):
            code, out, _err = run_main(["notes", "--since", "0.36.0", "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["installed"], "0.38.0")
        self.assertEqual(
            [item["version"] for item in payload["versions"]], ["0.37.0", "0.38.0"]
        )
        self.assertEqual(payload["versions"][0]["date"], "2026-11-10")
        self.assertIn("Mid release.", payload["versions"][0]["body"])

    def test_upgrade_prints_the_unseen_range_and_advances_the_marker(self) -> None:
        notes.write_seen("0.36.0")
        info = mock.Mock(method="pipx", upgradeable=True)
        with (
            mock.patch.object(admin, "detect", return_value=info),
            mock.patch.object(admin, "latest_version", return_value="0.38.0"),
            mock.patch.object(admin, "run_upgrade"),
            mock.patch.object(admin, "_post_upgrade_review"),
            mock.patch.object(notes, "has_release", return_value=True),
        ):
            code, out, _err = run_main(["upgrade"])
        self.assertEqual(code, 0)
        self.assertIn("upgraded lpui", out)
        self.assertIn("## v0.37.0", out)
        self.assertIn("## v0.38.0", out)
        self.assertEqual(notes.read_seen(), "0.38.0")

    def test_packaged_changelog_matches_the_root(self) -> None:
        self.assertEqual(
            (ROOT / "CHANGELOG.md").read_bytes(),
            (ROOT / "src/lazyplan/data/CHANGELOG.md").read_bytes(),
        )

    def test_changelog_gate_reports_the_regeneration_command(self) -> None:
        spec = importlib.util.spec_from_file_location(
            "check_changelog", ROOT / "tools/check-changelog.py"
        )
        assert spec is not None and spec.loader is not None
        tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tool)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "CHANGELOG.md"
            packaged = root / "src/lazyplan/data/CHANGELOG.md"
            source.write_text("# new\n", encoding="utf-8")
            packaged.parent.mkdir(parents=True)
            packaged.write_text("# old\n", encoding="utf-8")
            err = io.StringIO()
            with (
                mock.patch.object(tool, "SOURCE", source),
                mock.patch.object(tool, "PACKAGED", packaged),
                redirect_stderr(err),
            ):
                code = tool.main()
        self.assertEqual(code, 1)
        self.assertIn("cp CHANGELOG.md src/lazyplan/data/CHANGELOG.md", err.getvalue())


if __name__ == "__main__":
    unittest.main()
