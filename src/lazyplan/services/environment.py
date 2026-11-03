"""Environment use cases: upgrade detection and staged updates."""

from __future__ import annotations

from ..infrastructure.update_stage import (
    apply_on_launch,
    clear_failure,
    read_failure,
    stage_update,
)
from ..infrastructure.upgrade import (
    UPDATE_CACHE_TTL,
    InstallInfo,
    UpgradeError,
    cached_latest,
    detect,
    diagnostics,
    guard_message,
    latest_version,
    notice_text,
    parse_version,
    poll_interval,
    refresh_update,
    run_upgrade,
    update_check_enabled,
)

__all__ = [
    "UPDATE_CACHE_TTL",
    "InstallInfo",
    "UpgradeError",
    "apply_on_launch",
    "cached_latest",
    "clear_failure",
    "detect",
    "diagnostics",
    "guard_message",
    "latest_version",
    "notice_text",
    "parse_version",
    "poll_interval",
    "read_failure",
    "refresh_update",
    "run_upgrade",
    "stage_update",
    "update_check_enabled",
]
