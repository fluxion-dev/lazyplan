"""The lazyplan themes register, resolve, and expose every semantic token."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from lazyplan.store import Store

try:
    from lazyplan import tui as tui_mod
    from lazyplan.tui.theme import (
        DARK_NAME,
        DARK_TOKENS,
        LAZYPLAN_DARK,
        LAZYPLAN_LIGHT,
        LIGHT_NAME,
        LIGHT_TOKENS,
        TOKEN_NAMES,
        chart_color,
        choose_theme,
        lane_baseline_rgb,
        lane_rgb,
        token_rgb,
    )
except ImportError:  # pragma: no cover - stdlib-only interpreter
    tui_mod = None  # type: ignore[assignment]


@unittest.skipUnless(tui_mod is not None and tui_mod._TEXTUAL_OK, "textual not installed")
class ThemeTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "t.db")
        Store(self.db).add_plan("Plan")

    async def asyncTearDown(self) -> None:
        self.tmp.cleanup()

    def test_both_themes_share_the_semantic_token_set(self) -> None:
        self.assertEqual(tuple(LAZYPLAN_DARK.variables), TOKEN_NAMES)
        self.assertEqual(tuple(LAZYPLAN_LIGHT.variables), TOKEN_NAMES)
        self.assertEqual(set(DARK_TOKENS), set(LIGHT_TOKENS))
        self.assertEqual(LAZYPLAN_DARK.dark, True)
        self.assertEqual(LAZYPLAN_LIGHT.dark, False)

    def test_choose_theme_accepts_short_names_and_falls_back_to_dark(self) -> None:
        self.assertEqual(choose_theme("dark"), DARK_NAME)
        self.assertEqual(choose_theme("lazyplan-dark"), DARK_NAME)
        self.assertEqual(choose_theme("light"), LIGHT_NAME)
        self.assertEqual(choose_theme("lazyplan-light"), LIGHT_NAME)
        self.assertEqual(choose_theme("nonsense"), DARK_NAME)

    async def test_app_registers_both_themes_and_defaults_to_dark(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("LAZYPLAN_THEME", None)
            app = tui_mod.create_app(self.db)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            self.assertEqual(app.theme, DARK_NAME)
            self.assertIn(DARK_NAME, app.available_themes)
            self.assertIn(LIGHT_NAME, app.available_themes)
            self.assertEqual(app.theme_variables["lp-accent"], DARK_TOKENS["lp-accent"])

    async def test_env_selects_the_light_theme(self) -> None:
        with mock.patch.dict(os.environ, {"LAZYPLAN_THEME": "light"}):
            app = tui_mod.create_app(self.db)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            self.assertEqual(app.theme, LIGHT_NAME)
            self.assertFalse(app.current_theme.dark)
            self.assertEqual(app.theme_variables["lp-accent"], LIGHT_TOKENS["lp-accent"])

    async def test_chart_colors_follow_the_theme(self) -> None:
        with mock.patch.dict(os.environ, {"LAZYPLAN_THEME": "dark"}):
            app = tui_mod.create_app(self.db)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            self.assertEqual(chart_color(app), "green+")
            app.theme = LIGHT_NAME
            await pilot.pause()
            self.assertEqual(chart_color(app), "green")
            self.assertEqual(chart_color(app, "lp-chart-axis"), "gray")

    async def test_lane_baseline_rgb_blends_toward_the_surface(self) -> None:
        with mock.patch.dict(os.environ, {"LAZYPLAN_THEME": "dark"}):
            app = tui_mod.create_app(self.db)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            lane = lane_rgb(app, 0)
            surface = token_rgb(app, "lp-surface")
            baseline = lane_baseline_rgb(app, 0)
            self.assertNotEqual(baseline, lane)
            self.assertNotEqual(baseline, surface)
            for got, first, second in zip(baseline, lane, surface, strict=True):
                low, high = sorted((first, second))
                self.assertGreaterEqual(got, low)
                self.assertLessEqual(got, high)

    def test_chart_modules_do_not_hardcode_green(self) -> None:
        root = Path(__file__).resolve().parents[2] / "src" / "lazyplan" / "tui" / "metrics"
        for name in ("timeline.py",):
            text = (root / name).read_text(encoding="utf-8")
            self.assertNotIn('color="green"', text)

    async def test_every_token_resolves_in_both_themes(self) -> None:
        with mock.patch.dict(os.environ, {"LAZYPLAN_THEME": "dark"}):
            app = tui_mod.create_app(self.db)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            for name in TOKEN_NAMES:
                self.assertEqual(app.theme_variables[name], DARK_TOKENS[name])
            app.theme = LIGHT_NAME
            await pilot.pause()
            for name in TOKEN_NAMES:
                self.assertEqual(app.theme_variables[name], LIGHT_TOKENS[name])


if __name__ == "__main__":
    unittest.main()
