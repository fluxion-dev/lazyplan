"""Point every home lookup at a temp dir, on posix and Windows alike.

`Path.home()` reads HOME on posix but USERPROFILE on Windows, and the shared
home follows LOCALAPPDATA on Windows. Setting HOME alone leaves a Windows run
writing into the real profile.
"""

from __future__ import annotations

import os
import unittest
from collections.abc import MutableMapping
from pathlib import Path


def _home_vars(path: str | Path) -> dict[str, str | None]:
    home = str(path)
    return {"HOME": home, "USERPROFILE": home, "LOCALAPPDATA": None}


def _put(env: MutableMapping[str, str], key: str, value: str | None) -> None:
    if value is None:
        env.pop(key, None)
    else:
        env[key] = value


def sandbox_home(case: unittest.TestCase, path: str | Path) -> None:
    """Sandbox this process's home for one test; restored on cleanup."""
    for key, value in _home_vars(path).items():
        case.addCleanup(_put, os.environ, key, os.environ.get(key))
        _put(os.environ, key, value)


def sandbox_env(env: MutableMapping[str, str], path: str | Path) -> MutableMapping[str, str]:
    """Sandbox the home of a child process environment in place."""
    for key, value in _home_vars(path).items():
        _put(env, key, value)
    return env
