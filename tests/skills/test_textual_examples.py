"""Headless checks for the runnable Textual skill examples."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from types import ModuleType

from tests.support.paths import ROOT

try:
    from textual.app import App

    _TEXTUAL_OK = True
except ImportError:  # stdlib-only interpreter
    _TEXTUAL_OK = False

EXAMPLES = ROOT / ".agents/skills"


def load(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def app_for(skill: str, filename: str, name: str, app_name: str) -> App:
    module = load(EXAMPLES / skill / "examples" / filename, name)
    return getattr(module, app_name)()


@unittest.skipUnless(_TEXTUAL_OK, "textual not installed")
class TestTextualSkillExamples(unittest.IsolatedAsyncioTestCase):
    async def test_widget_gallery_mounts(self):
        from textual.widgets import DataTable, Input, Tree

        app = app_for("textual-widgets", "widget_gallery.py", "widget_gallery", "WidgetGallery")
        async with app.run_test() as pilot:
            await pilot.pause()
            self.assertTrue(app.query_one("#filter", Input))
            self.assertTrue(app.query_one("#table", DataTable))
            self.assertTrue(app.query_one("#tree", Tree))

    async def test_style_states_apply_a_class(self):
        app = app_for("textual-styles", "style_states.py", "style_states", "StyleStates")
        async with app.run_test() as pilot:
            await pilot.pause()
            self.assertTrue(app.query_one("#box").has_class("active"))

    async def test_event_log_handles_key_and_message(self):
        from textual.widgets import Static

        app = app_for("textual-events", "event_log.py", "event_log", "EventLog")
        async with app.run_test() as pilot:
            await pilot.press("s")
            await pilot.pause()
            self.assertEqual(str(app.query_one("#log", Static).render()), "saved")

    async def test_css_type_example_mounts(self):
        app = app_for("textual-css-types", "type_values.py", "type_values", "TypeValues")
        async with app.run_test() as pilot:
            await pilot.pause()
            self.assertTrue(app.query_one("#card"))

    async def test_layout_shell_mounts(self):
        from textual.containers import Horizontal, VerticalScroll

        app = app_for("textual-layout", "layout_shell.py", "layout_shell", "LayoutShell")
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            self.assertTrue(app.query_one("#main", Horizontal))
            self.assertTrue(app.query_one("#preview", VerticalScroll))

    async def test_guided_app_mounts(self):
        from textual.widgets import Static

        app = app_for("textual-guides", "guided_app.py", "guided_app", "GuidedApp")
        async with app.run_test() as pilot:
            await pilot.pause()
            self.assertEqual(str(app.query_one("#body", Static).render()), "guide example")


if __name__ == "__main__":
    unittest.main()
