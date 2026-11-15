"""Theme precedence and memory: environment, then saved setup, then default."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from lazyplan.presentation.setup.state import SetupState, load_state, save_state
from tests.support.home import sandbox_home

try:
    from lazyplan.presentation.tui import create_app
    from lazyplan.presentation.tui.theme import themes
except ImportError:  # pragma: no cover - textual not installed
    create_app = None  # type: ignore[assignment]
    themes = None  # type: ignore[assignment]


class FakeApp:
    """The two attributes ``register_themes`` uses."""

    def __init__(self) -> None:
        self.registered: list[str] = []
        self.theme = ""

    def register_theme(self, theme: object) -> None:
        self.registered.append(str(getattr(theme, "name", theme)))


@unittest.skipUnless(create_app is not None, "textual not installed")
class ThemeChoiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        self.home.mkdir()
        sandbox_home(self, self.home)
        self.old = os.environ.pop(themes.ENV_VAR, None)

    def tearDown(self) -> None:
        if self.old is None:
            os.environ.pop(themes.ENV_VAR, None)
        else:
            os.environ[themes.ENV_VAR] = self.old
        self.tmp.cleanup()

    def test_the_default_is_mocha(self) -> None:
        self.assertEqual(themes.choose_theme(), themes.DARK_NAME)

    def test_aliases_resolve_to_canonical_names(self) -> None:
        for raw, expected in (
            ("dark", themes.DARK_NAME),
            ("void", themes.VOID_NAME),
            ("oled", themes.VOID_NAME),
            ("latte", themes.LIGHT_NAME),
            ("lazyplan_light", themes.LIGHT_NAME),
            ("nope", themes.DARK_NAME),
        ):
            with self.subTest(raw=raw):
                self.assertEqual(themes.choose_theme(raw), expected)

    def test_a_remembered_theme_applies_without_the_environment(self) -> None:
        self.assertEqual(themes.choose_theme(themes.VOID_NAME), themes.VOID_NAME)
        self.assertEqual(themes.choose_theme("latte"), themes.LIGHT_NAME)

    def test_the_environment_beats_the_remembered_theme(self) -> None:
        with mock.patch.dict(os.environ, {themes.ENV_VAR: "latte"}):
            self.assertEqual(themes.choose_theme(themes.VOID_NAME), themes.LIGHT_NAME)

    def test_register_themes_activates_the_remembered_choice(self) -> None:
        app = FakeApp()
        selected = themes.register_themes(app, themes.LIGHT_NAME)
        self.assertEqual(selected, themes.LIGHT_NAME)
        self.assertEqual(app.theme, themes.LIGHT_NAME)
        self.assertEqual(app.registered, list(themes.THEME_NAMES))

    def test_the_environment_still_wins_at_registration(self) -> None:
        with mock.patch.dict(os.environ, {themes.ENV_VAR: "void"}):
            app = FakeApp()
            self.assertEqual(themes.register_themes(app, themes.LIGHT_NAME), themes.VOID_NAME)
        self.assertEqual(app.theme, themes.VOID_NAME)

    def test_remembering_writes_canonical_names_and_ignores_the_environment(self) -> None:
        with mock.patch.dict(os.environ, {themes.ENV_VAR: "void"}):
            stored = themes.remember_theme("latte", self.home)
        self.assertEqual(stored, themes.LIGHT_NAME)
        self.assertEqual(load_state(self.home).theme, themes.LIGHT_NAME)
        self.assertEqual(themes.remembered_theme(self.home), themes.LIGHT_NAME)

    def test_a_saved_theme_survives_a_state_round_trip(self) -> None:
        save_state(SetupState(theme=themes.VOID_NAME), self.home)
        self.assertEqual(themes.remembered_theme(self.home), themes.VOID_NAME)

    def test_an_old_state_file_without_a_theme_defaults_safely(self) -> None:
        path = Path(self.home) / ".lazyplan/setup.json"
        path.parent.mkdir(parents=True)
        path.write_text('{"placement": "home"}', encoding="utf-8")
        self.assertEqual(themes.remembered_theme(self.home), "")
        self.assertEqual(themes.choose_theme(themes.remembered_theme(self.home)), themes.DARK_NAME)

    def test_the_wizard_prefills_the_saved_theme(self) -> None:
        from lazyplan.presentation.setup.session import SetupSession

        themes.remember_theme("latte", self.home)
        with mock.patch("lazyplan.infrastructure.host_models.discover_all", return_value={}):
            session = SetupSession.load(self.home, self.home, "1.0")
        self.assertEqual(session.draft.theme, themes.LIGHT_NAME)
        self.assertEqual(session.draft.theme, load_state(self.home).theme)


@unittest.skipUnless(create_app is not None, "textual not installed")
class ThemeCycleTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        root = Path(self.tmp.name)
        self.home = root / "home"
        self.home.mkdir()
        sandbox_home(self, self.home)
        self.old = os.environ.pop(themes.ENV_VAR, None)
        self.db = str(root / "plans.db")

    def tearDown(self) -> None:
        if self.old is not None:
            os.environ[themes.ENV_VAR] = self.old
        self.tmp.cleanup()

    async def test_the_cycle_saves_the_next_theme(self) -> None:
        app = create_app(self.db)
        self.assertEqual(app.theme, themes.DARK_NAME)
        async with app.run_test(size=(110, 40)) as pilot:
            await pilot.press("t")
            await pilot.pause()
        self.assertEqual(app.theme, themes.VOID_NAME)
        self.assertEqual(load_state(self.home).theme, themes.VOID_NAME)

    async def test_the_saved_theme_opens_the_next_launch(self) -> None:
        save_state(SetupState(theme=themes.LIGHT_NAME), self.home)
        app = create_app(self.db)
        self.assertEqual(app.theme, themes.LIGHT_NAME)

    async def test_the_environment_beats_the_saved_theme_at_launch(self) -> None:
        save_state(SetupState(theme=themes.LIGHT_NAME), self.home)
        with mock.patch.dict(os.environ, {themes.ENV_VAR: "void"}):
            app = create_app(self.db)
        self.assertEqual(app.theme, themes.VOID_NAME)


if __name__ == "__main__":
    unittest.main()
