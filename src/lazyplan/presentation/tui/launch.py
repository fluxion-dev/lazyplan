"""Launch-time update handling for the TUI."""

from __future__ import annotations

import os
import sys

from ...infrastructure.environment import apply_on_launch, clear_failure, read_failure
from ..cli.parser import package_version


def launch_update() -> tuple[str, bool]:
    """Apply or hand off a staged update; return (notice, exit_now)."""
    state, detail = apply_on_launch(package_version())
    if state == "applying":
        print(f"update applying in the background; log: {detail}", file=sys.stderr)
        return "", True
    startup_notice = ""
    if state == "applied":
        try:
            os.execv(sys.executable, [sys.executable, "-m", "lazyplan", *sys.argv[1:]])
        except OSError as exc:
            startup_notice = f"update v{detail} installed — restart lpui ({exc})"
    elif state == "error":
        startup_notice = f"update failed: {detail}"
    elif state == "downgrade":
        startup_notice = f"refused to downgrade to v{detail}"
    else:
        failure = read_failure()
        if failure:
            startup_notice = f"update failed: {failure}"
            clear_failure()
    return startup_notice, False
