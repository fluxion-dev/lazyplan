"""Icon palette precedence, shared maps, and the TUI cycle."""

from __future__ import annotations

import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from lazyplan.presentation.cli import main as lpui_main
from lazyplan.presentation.setup.state import SetupState, load_state, save_state
from lazyplan.presentation.shared import design
from lazyplan.store import Store
from tests.support.home import sandbox_home

try:
    from lazyplan.presentation.tui import create_app
except ImportError:  # pragma: no cover - textual not installed
    create_app = None  # type: ignore[assignment]


class IconPaletteTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.home = Path(self.tmp.name) / "home"
        self.home.mkdir()
        sandbox_home(self, self.home)
        self.db = str(Path(self.tmp.name) / "plans.db")
        self.old = os.environ.pop(design.ICON_ENV, None)
        self.addCleanup(design.apply_icons, design.DEFAULT_ICONS)

    def tearDown(self) -> None:
        if self.old is None:
            os.environ.pop(design.ICON_ENV, None)
        else:
            os.environ[design.ICON_ENV] = self.old
        self.tmp.cleanup()

    def test_the_default_is_classic(self) -> None:
        self.assertEqual(design.choose_icons(), design.DEFAULT_ICONS)
        self.assertEqual(design.active_icons(), design.DEFAULT_ICONS)

    def test_aliases_resolve_to_canonical_names(self) -> None:
        for raw, expected in (
            ("default", "classic"),
            ("circles", "orbit"),
            ("squares", "blocks"),
            ("ticks", "marks"),
            ("plain", "ascii"),
            ("nope", ""),
        ):
            with self.subTest(raw=raw):
                self.assertEqual(design.resolve_icons(raw), expected)

    def test_every_palette_covers_the_same_keys(self) -> None:
        first = design.ICON_PALETTES[0]
        for palette in design.ICON_PALETTES:
            with self.subTest(palette=palette.name):
                self.assertEqual(set(palette.icons), set(first.icons))
                self.assertEqual(set(palette.status), set(first.status))
                self.assertEqual(set(palette.kind), set(first.kind))
                self.assertEqual(set(palette.section), set(first.section))
                self.assertEqual(set(palette.state), set(first.state))
                for name in ("icons", "status", "kind", "section", "state"):
                    self.assertTrue(all(getattr(palette, name).values()))

    def test_the_environment_beats_the_remembered_palette(self) -> None:
        with mock.patch.dict(os.environ, {design.ICON_ENV: "marks"}):
            self.assertEqual(design.choose_icons("blocks"), "marks")

    def test_apply_icons_updates_every_shared_map(self) -> None:
        self.assertEqual(design.apply_icons("blocks"), "blocks")
        self.assertEqual(design.active_icons(), "blocks")
        self.assertEqual(design.status_word("todo"), "□")
        self.assertEqual(design.status_word("doing"), "◪")
        self.assertEqual(design.STATUS_GLYPH["done"], "■")
        self.assertEqual(design.KIND_ICON["plan"], "◆")
        self.assertEqual(design.SECTION_ICON["git"], "⎇")
        self.assertEqual(design.STATE_ICON["dirty"], "■")

    def test_select_icons_resolves_and_applies(self) -> None:
        with mock.patch.dict(os.environ, {design.ICON_ENV: "ascii"}):
            self.assertEqual(design.select_icons("orbit"), "ascii")
        self.assertEqual(design.status_word("doing"), "+")

    def test_remembering_writes_canonical_names_and_ignores_the_environment(self) -> None:
        with mock.patch.dict(os.environ, {design.ICON_ENV: "blocks"}):
            stored = design.remember_icons("plain", self.home)
        self.assertEqual(stored, "ascii")
        self.assertEqual(load_state(self.home).icons, "ascii")
        self.assertEqual(design.remembered_icons(self.home), "ascii")

    def test_a_saved_palette_survives_a_state_round_trip(self) -> None:
        save_state(SetupState(icons="orbit"), self.home)
        self.assertEqual(design.remembered_icons(self.home), "orbit")

    def test_an_old_state_file_without_icons_defaults_safely(self) -> None:
        path = Path(self.home) / ".lazyplan/setup.json"
        path.parent.mkdir(parents=True)
        path.write_text('{"placement": "home"}', encoding="utf-8")
        self.assertEqual(design.remembered_icons(self.home), "")
        self.assertEqual(design.choose_icons(design.remembered_icons(self.home)), "classic")

    def test_the_cli_draws_the_environment_palette(self) -> None:
        Store(self.db).add_plan("Demo")
        buf = io.StringIO()
        with mock.patch.dict(os.environ, {design.ICON_ENV: "blocks"}):
            with redirect_stdout(buf):
                self.assertEqual(lpui_main(["--db", self.db, "list"]), 0)
        self.assertIn("□ P1 Demo", buf.getvalue())

    def test_the_cli_draws_the_remembered_palette(self) -> None:
        Store(self.db).add_plan("Demo")
        save_state(SetupState(icons="ascii"), self.home)
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(lpui_main(["--db", self.db, "list"]), 0)
        self.assertIn(". P1 Demo", buf.getvalue())

    def test_the_wizard_prefills_the_saved_palette(self) -> None:
        from lazyplan.presentation.setup.session import SetupSession

        design.remember_icons("marks", self.home)
        with mock.patch("lazyplan.infrastructure.host_models.discover_all", return_value={}):
            session = SetupSession.load(self.home, self.home, "1.0")
        self.assertEqual(session.draft.icons, "marks")


@unittest.skipUnless(create_app is not None, "textual not installed")
class IconCycleTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        root = Path(self.tmp.name)
        self.home = root / "home"
        self.home.mkdir()
        sandbox_home(self, self.home)
        self.db = str(root / "plans.db")
        self.old = os.environ.pop(design.ICON_ENV, None)
        self.addCleanup(design.apply_icons, design.DEFAULT_ICONS)

    def tearDown(self) -> None:
        if self.old is not None:
            os.environ[design.ICON_ENV] = self.old
        self.tmp.cleanup()

    async def test_the_cycle_saves_the_next_palette(self) -> None:
        app = create_app(self.db)
        self.assertEqual(design.active_icons(), "classic")
        async with app.run_test(size=(110, 40)) as pilot:
            await pilot.press("i")
            await pilot.pause()
        self.assertEqual(design.active_icons(), "orbit")
        self.assertEqual(load_state(self.home).icons, "orbit")

    async def test_the_saved_palette_opens_the_next_launch(self) -> None:
        save_state(SetupState(icons="marks"), self.home)
        create_app(self.db)
        self.assertEqual(design.active_icons(), "marks")
        self.assertEqual(design.STATUS_GLYPH["done"], "✓")


if __name__ == "__main__":
    unittest.main()
