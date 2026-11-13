"""Process liveness without a third-party library.

A PID alone is not identity: the operating system reuses ids. When the
platform exposes a start stamp, it is stored with the PID and compared before
a row is declared dead. Unknown liveness is treated as alive, so a missing
probe never closes work.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_STILL_ACTIVE = 259
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def process_start(pid: int) -> str:
    """A stable start stamp for one live process, or an empty string."""
    if pid <= 0:
        return ""
    if sys.platform.startswith("linux"):
        return _linux_start(pid)
    if os.name == "nt":
        return _windows_start(pid)
    return ""


def process_alive(pid: int, start: str = "") -> bool | None:
    """True when *pid* runs with the same start stamp; None when unprovable."""
    if pid <= 0:
        return None
    alive = _alive(pid)
    if alive is not True:
        return alive
    stamp = process_start(pid)
    if start and stamp:
        return stamp == start
    return True


def _alive(pid: int) -> bool | None:
    """Raw liveness from the operating system."""
    if os.name == "nt":
        return _windows_alive(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return None
    return True


def _linux_start(pid: int) -> str:
    """Field 22 of /proc/<pid>/stat: start time in clock ticks since boot."""
    try:
        text = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    except OSError:
        return ""
    end = text.rfind(")")
    if end < 0:
        return ""
    fields = text[end + 2 :].split()
    return fields[19] if len(fields) > 19 else ""


def _windows_alive(pid: int) -> bool | None:
    """OpenProcess plus GetExitCodeProcess; access denied still means alive."""
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return None
        try:
            code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return None
            return int(code.value) == _STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    except (AttributeError, OSError, ValueError):
        return None


def _windows_start(pid: int) -> str:
    """Creation time as a FILETIME integer, or an empty string."""
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return ""
        try:
            created = wintypes.FILETIME()
            exited = wintypes.FILETIME()
            kernel = wintypes.FILETIME()
            user = wintypes.FILETIME()
            if not kernel32.GetProcessTimes(
                handle,
                ctypes.byref(created),
                ctypes.byref(exited),
                ctypes.byref(kernel),
                ctypes.byref(user),
            ):
                return ""
            return str((int(created.dwHighDateTime) << 32) | int(created.dwLowDateTime))
        finally:
            kernel32.CloseHandle(handle)
    except (AttributeError, OSError, ValueError):
        return ""
