"""Update modal: method-specific copy for uv, pipx, and guarded installs."""

from __future__ import annotations

import unittest

from lazyplan.infrastructure.upgrade import PIPX, UV, InstallInfo

try:
    from lazyplan.presentation.tui.screens import UpdateScreen
except ImportError:  # pragma: no cover - textual not installed
    UpdateScreen = None  # type: ignore[assignment,misc]

UV_INFO = InstallInfo(UV, True, "/home/u/.local/share/uv/tools/lazyplan-tui")
PIPX_INFO = InstallInfo(PIPX, True, "/home/u/.local/share/pipx/venvs/lazyplan-tui")
GUARDED = InstallInfo("rpm", False, "system rpm install")


@unittest.skipUnless(UpdateScreen is not None, "textual not installed")
class TestUpdateScreen(unittest.TestCase):
    def test_uv_body_names_the_method_and_the_windows_apply_step(self):
        screen = UpdateScreen("0.51.1", "0.52.0", UV_INFO, windows=True)
        body = screen._body()
        self.assertIn("method     uv", body)
        self.assertIn("restart to apply", body)

    def test_uv_is_offered_a_download(self):
        screen = UpdateScreen("0.51.1", "0.52.0", UV_INFO, windows=False)
        self.assertTrue(screen.info.upgradeable)
        self.assertIn("next time lpui starts", screen._body())

    def test_pipx_body_names_the_method(self):
        screen = UpdateScreen("0.51.1", "0.52.0", PIPX_INFO, windows=False)
        self.assertIn("method     pipx", screen._body())

    def test_guarded_install_shows_the_guard(self):
        screen = UpdateScreen("0.51.1", "0.52.0", GUARDED, windows=True)
        self.assertIn("package manager", screen._body())
