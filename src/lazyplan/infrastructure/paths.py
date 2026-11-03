"""Platform path defaults: Downloads folders and user-dir configuration."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path


def _home(env: Mapping[str, str]) -> Path:
    return Path(env.get("USERPROFILE") or env.get("HOME") or Path.home())


def _download_from_user_dirs(env: Mapping[str, str], home: Path) -> Path | None:
    config_home = Path(env.get("XDG_CONFIG_HOME") or home / ".config")
    try:
        lines = (config_home / "user-dirs.dirs").read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in lines:
        if not line.startswith("XDG_DOWNLOAD_DIR="):
            continue
        raw = line.partition("=")[2].strip().strip('"')
        if not raw:
            return None
        return Path(raw.replace("$HOME", str(home))).expanduser()
    return None


def download_dir(env: Mapping[str, str] | None = None) -> Path | None:
    """Return the existing platform Downloads folder, or None."""
    environ = os.environ if env is None else env
    home = _home(environ)
    configured = environ.get("XDG_DOWNLOAD_DIR", "").strip()
    candidates = [
        Path(configured.replace("$HOME", str(home))).expanduser() if configured else None,
        _download_from_user_dirs(environ, home),
        home / "Downloads",
    ]
    for candidate in candidates:
        if candidate is not None and candidate.is_dir():
            return candidate
    return None
