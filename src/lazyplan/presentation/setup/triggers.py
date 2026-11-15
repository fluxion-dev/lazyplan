"""Decide when the setup wizard is due, and remember the answer.

The trigger is pure apart from the two live probes: pending catalog items and
broken managed profiles. ``detect`` never writes; ``mark_pending`` and
``clear_pending`` own the setup-state fields the CLI and the screen share.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from lazyplan.infrastructure import agent_install
from lazyplan.infrastructure.repo import find_repo_root, repo_plan_db_path, shared_db_path

from .apply import choice_from_state
from .constants import REPO
from .integrations import inspect
from .layout import SetupChoice
from .state import SetupState, load_state, save_state

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
    agents = choice.agents or state.agents
    if not (state.skills_enabled and state.profile_files and agents):
        return False
    scope = "project" if state.placement == REPO and root is not None else "global"
    db_path = (
        repo_plan_db_path(root) if scope == "project" and root is not None else shared_db_path(home)
    )
    disk = agent_install.inspect_profiles(scope, root, home, agents, db_path)
    return disk.broken
