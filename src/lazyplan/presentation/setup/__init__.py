"""First-run setup: state, findings, wizard, layout, and apply."""

from __future__ import annotations

import sys

from lazyplan.infrastructure import hook_install
from lazyplan.infrastructure.repo import shared_db_path as shared_db_path

from . import layout, ui
from .apply import (
    apply_choice,
    choice_from_state,
    ensure,
    install_hooks,
    install_integrations,
    install_pointer,
    refresh_installed_hooks,
    refresh_integrations,
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
from .integrations import (
    Inspection,
    ReviewResult,
    inspect,
    remember_installed,
    review_pending,
)
from .layout import SetupChoice, SetupLayout
from .moves import move_repo_db
from .session import SetupDraft, SetupSession, SetupSessionError
from .state import SetupState, git_state, load_state, plans_in, save_state, state_path
from .steps import Step, visible_steps
from .triggers import WizardNeed, clear_pending, detect, mark_pending, pending_reason
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
    "Inspection",
    "ReviewResult",
    "SetupChoice",
    "SetupDraft",
    "SetupLayout",
    "SetupSession",
    "SetupSessionError",
    "SetupState",
    "Step",
    "WizardNeed",
    "apply_choice",
    "choice_from_args",
    "choice_from_state",
    "cleanup_repo_artifacts",
    "clear_pending",
    "default_choice",
    "detect",
    "detect_findings",
    "ensure",
    "git_state",
    "inspect",
    "install_hooks",
    "install_integrations",
    "install_pointer",
    "layout",
    "load_state",
    "mark_pending",
    "move_repo_db",
    "pending_reason",
    "plans_in",
    "preview",
    "refresh_installed_hooks",
    "refresh_installed_skills",
    "refresh_integrations",
    "remember_installed",
    "review_findings",
    "review_pending",
    "run_wizard",
    "save_state",
    "setup_layout",
    "setup_ui",
    "state_path",
    "ui",
    "visible_steps",
]
