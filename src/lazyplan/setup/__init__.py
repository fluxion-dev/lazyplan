"""First-run setup: state, findings, wizard, layout, and apply."""

from __future__ import annotations

import sys

from .. import hook_install as hook_install
from ..repo import shared_db_path as shared_db_path
from . import layout, ui
from .apply import (
    apply_choice,
    ensure,
    install_hooks,
    install_integrations,
    install_pointer,
)
from .constants import (
    HOME,
    HUMAN_COMMANDS,
    NO_SETUP_ENV,
    REPO,
    SETUP_VERSION,
    SKIP_COMMANDS,
    STATE_NAME,
)
from .findings import (
    Finding,
    choice_from_args,
    cleanup_repo_artifacts,
    default_choice,
    detect_findings,
    preview,
    refresh_installed_skills,
    review_findings,
)
from .findings import (
    legacy_db_findings as legacy_db_findings,
)
from .layout import SetupChoice, SetupLayout
from .moves import move_repo_db
from .state import SetupState, git_state, load_state, plans_in, save_state, state_path
from .wizard import run_wizard

setup_layout = layout
setup_ui = ui

__all__ = [
    "legacy_db_findings",
    "shared_db_path",
    "hook_install",
    "sys",
    "STATE_NAME",
    "SKIP_COMMANDS",
    "REPO",
    "NO_SETUP_ENV",
    "HUMAN_COMMANDS",
    "HOME",
    "SETUP_VERSION",
    "Finding",
    "SetupChoice",
    "SetupLayout",
    "SetupState",
    "apply_choice",
    "choice_from_args",
    "cleanup_repo_artifacts",
    "default_choice",
    "detect_findings",
    "ensure",
    "git_state",
    "install_hooks",
    "install_integrations",
    "install_pointer",
    "layout",
    "load_state",
    "move_repo_db",
    "plans_in",
    "preview",
    "refresh_installed_skills",
    "review_findings",
    "run_wizard",
    "save_state",
    "setup_layout",
    "setup_ui",
    "state_path",
    "ui",
]
