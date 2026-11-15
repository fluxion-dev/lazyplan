"""Decide when the setup wizard is due, and remember the answer.

The trigger is pure apart from the two live probes: pending catalog items and
broken managed profiles. ``detect`` never writes; ``mark_pending`` and
``clear_pending`` own the setup-state fields the CLI and the screen share.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lazyplan.infrastructure.repo import find_repo_root

from . import ui
from .apply import choice_from_state, profile_drift
from .constants import NO_SETUP_ENV
from .integrations import inspect
from .layout import SetupChoice
from .state import SetupState, load_state, save_state

UI_COMMAND = "ui"
FRESH = "fresh"
VERSION = "version"
INTEGRATIONS = "integrations"
PROFILES = "profiles"
REQUEST = "request"
REASONS: tuple[str, ...] = (FRESH, VERSION, INTEGRATIONS, PROFILES, REQUEST)
DEFAULT_DETAILS: dict[str, str] = {
    FRESH: "finish setting lazyplan up",
    VERSION: "this release changed setup",
    INTEGRATIONS: "new skills or hooks are available",
    PROFILES: "managed agent profiles are missing or out of date",
    REQUEST: "opened from the screen",
}


@dataclass(frozen=True)
class WizardNeed:
    """Whether setup should open, and the reason to show the user."""

    reason: str = ""
    version: str = ""
    detail: str = ""

    @property
    def due(self) -> bool:
        """True when a reason needs the wizard."""
        return bool(self.reason)

    def to_dict(self) -> dict[str, object]:
        """JSON-safe payload for the screen and diagnostics."""
        return {
            "due": self.due,
            "reason": self.reason,
            "version": self.version,
            "detail": self.detail,
        }


def pending_reason(
    state: SetupState,
    version: str,
    *,
    pending_integrations: bool = False,
    profile_drift: bool = False,
) -> str:
    """Return the remembered or version-based reason, before live probes."""
    if state.wizard_pending:
        return state.wizard_pending if state.wizard_pending in REASONS else VERSION
    if not state.wizard_completed:
        return FRESH if not state.last_version else VERSION
    if state.wizard_completed != version:
        return VERSION
    if pending_integrations:
        return INTEGRATIONS
    if profile_drift:
        return PROFILES
    return ""


def detect(
    cwd: Path,
    home: Path | None = None,
    version: str = "",
    state: SetupState | None = None,
    requested: bool = False,
) -> WizardNeed:
    """Decide whether the wizard is due for this checkout, without writing."""
    home = home or Path.home()
    state = state or load_state(home)
    root = find_repo_root(cwd)
    if requested:
        return WizardNeed(REQUEST, version, DEFAULT_DETAILS[REQUEST])
    reason = pending_reason(state, version)
    if reason:
        return WizardNeed(reason, version, DEFAULT_DETAILS[reason])
    choice = choice_from_state(state)
    if _pending_items(choice, state, root, home, version):
        return WizardNeed(INTEGRATIONS, version, DEFAULT_DETAILS[INTEGRATIONS])
    if _profile_drift(choice, state, root, home):
        return WizardNeed(PROFILES, version, DEFAULT_DETAILS[PROFILES])
    return WizardNeed("", version)


def mark_pending(
    state: SetupState,
    reason: str,
    version: str,
    home: Path,
) -> SetupState:
    """Record why the wizard should open and persist it."""
    state.wizard_pending = reason if reason in REASONS else VERSION
    state.wizard_version = version
    save_state(state, home)
    return state


def clear_pending(state: SetupState, version: str, home: Path) -> SetupState:
    """Record a completed wizard and persist the cleared marker."""
    state.wizard_pending = ""
    state.wizard_version = ""
    state.wizard_completed = version
    save_state(state, home)
    return state


def textual_available() -> bool:
    """True when the optional Textual dependency can be imported."""
    try:
        return importlib.util.find_spec("textual") is not None
    except (ImportError, ValueError):  # pragma: no cover - broken install
        return False


def setup_off(db_path: str | None = None) -> bool:
    """True when a caller-owned database or ``LAZYPLAN_NO_SETUP`` turns setup off."""
    explicit = db_path or os.environ.get("LAZYPLAN_DB", "")
    return bool(str(explicit).strip() or os.environ.get(NO_SETUP_ENV, "").strip())


def _screen_terminal(interactive: bool | None) -> bool:
    """Whether this run has the terminal the full screen needs."""
    if interactive is not None:
        return interactive
    try:
        return ui.stdin_tty() and sys.stderr.isatty() and sys.stdout.isatty()
    except (AttributeError, ValueError):
        return False


def tui_owns_setup(
    cmd: str | None,
    args: Any,
    interactive: bool | None = None,
) -> bool:
    """Whether the TUI wizard, not the terminal one, owns setup for this run.

    Only an interactive ``ui`` run with Textual installed defers; every other
    command keeps the terminal path, and ``--json`` and ``--yes`` stay silent.
    """
    if cmd != UI_COMMAND:
        return False
    if getattr(args, "json", False) or getattr(args, "yes", False):
        return False
    return _screen_terminal(interactive) and textual_available()


def defer_to_tui(home: Path, version: str, fresh: bool) -> WizardNeed:
    """Remember why the TUI wizard is pending and return the reason."""
    reason = FRESH if fresh else VERSION
    mark_pending(load_state(home), reason, version, home)
    return WizardNeed(reason, version, DEFAULT_DETAILS[reason])


def _pending_items(
    choice: SetupChoice,
    state: SetupState,
    root: Path | None,
    home: Path,
    version: str,
) -> tuple[object, ...]:
    """Catalog items a release added but setup has not installed."""
    return inspect(choice, state, root, home, version).pending


def _profile_drift(
    choice: SetupChoice,
    state: SetupState,
    root: Path | None,
    home: Path,
) -> bool:
    """True when managed profiles are missing or no longer match their render."""
    disk = profile_drift(choice, state, root, home)
    return bool(disk and disk.broken)
